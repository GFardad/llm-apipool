from __future__ import annotations

import json
import time
import uuid
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

from llm_keypool.api.routes.responses import ResponsesRequest, build_response_object, to_chat_messages, to_chat_tools
from llm_keypool.providers.dispatch import _estimate_tokens, complete as dispatch_complete

MAX_RETRIES = 20


class _ChatRequest(BaseModel):
    model: str | None = None
    messages: list[dict[str, Any]]
    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    stream: bool | None = False
    stop: str | list[str] | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    seed: int | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    reasoning_effort: str | None = None
    response_format: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    user: str | None = None
    unicid: str | None = None


def _openai_error(status: int, message: str, err_type: str = "provider_error") -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"message": message, "type": err_type, "code": str(status)}},
    )


def _normalize_chunk(chunk: dict[str, Any], resp_id: str, created: int, model: str) -> None:
    if "id" not in chunk:
        chunk["id"] = resp_id
    if "created" not in chunk:
        chunk["created"] = created
    if "model" not in chunk:
        chunk["model"] = model


def _create_chat_router(store, rotator, configs, default_capabilities):
    router = APIRouter()
    @router.post("/v1/chat/completions")
    async def chat_completions(
        req: _ChatRequest,
        x_keypool_capabilities: Annotated[str | None, Header()] = None,
        x_subscriber_id: Annotated[str | None, Header()] = None,
    ) -> Any:
        from llm_keypool.core.model_parser import ModelParser
        from llm_keypool.group_routing import extract_group, parse_context_filter

        if x_keypool_capabilities:
            caps = [c.strip() for c in x_keypool_capabilities.split(",") if c.strip()]
        else:
            caps = default_capabilities

        subscriber = x_subscriber_id or "proxy"

        model_param = req.model or "default"

        # When force_provider is active, override everything to the forced model
        if rotator.force_provider:
            forced_key_data = rotator.get_best_key(caps if caps else default_capabilities, subscriber_id=subscriber)
            forced_model = (forced_key_data or {}).get("model", "deepseek-v4-flash-free")
            model_param = forced_model

        group = extract_group(model_param)
        context_filter = parse_context_filter(model_param)
        min_context = None
        if context_filter:
            group, min_context = context_filter

        base_model, model_filter, strategy_override = ModelParser.parse(model_param)
        min_context = min_context or model_filter.context_min
        require_tools = model_filter.tools
        require_vision = model_filter.vision

        kwargs: dict[str, Any] = {}
        # When force_provider is active, the provider's model is authoritative
        # and must NOT be overridden by the user's requested model
        if not rotator.force_provider and model_param not in ("auto", "default"):
            kwargs["model"] = model_param
        # Forward all supported OpenAI params from the request to dispatch
        for _field in ("max_tokens", "temperature", "top_p", "stop",
                       "frequency_penalty", "presence_penalty", "seed",
                       "tools", "tool_choice", "reasoning_effort",
                       "response_format", "metadata", "user"):
            val = getattr(req, _field, None)
            if val is not None:
                kwargs[_field] = val

        resp_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created = int(time.time())

        if req.stream:
            gen, key_data = await dispatch_complete(
                rotator,
                capabilities=caps,
                messages=req.messages,
                subscriber_id=subscriber,
                stream=True,
                min_context=min_context,
                require_tools=require_tools,
                require_vision=require_vision,
                **kwargs,
            )
            if key_data is None:
                return _openai_error(503, "All available keys exhausted", "server_error")

            model_used = key_data.get("model", "unknown") if rotator.force_provider else (
                model_param if model_param not in ("auto", "default") else key_data.get("model", "unknown")
            )
            provider_used = key_data.get("provider", "unknown")

            if req.unicid and key_data.get("is_sticky_enabled"):
                store.create_sticky_session(
                    req.unicid,
                    key_data["key_id"],
                    key_data["provider"],
                    key_data.get("model"),
                    key_data.get("sticky_ttl_hours", 1),
                )

            # Peek first chunk to detect provider errors before starting SSE
            first_chunk = None
            rest_chunks: list[dict[str, Any]] = []

            async for chunk in gen:
                if first_chunk is None:
                    first_chunk = chunk
                else:
                    rest_chunks.append(chunk)
                break

            if first_chunk is None:
                return _openai_error(502, "Provider returned empty stream", "provider_error")

            x_err = first_chunk.get("x_error")
            if x_err:
                return _openai_error(502, x_err, "provider_error")

            async def _stream() -> AsyncGenerator[str, None]:
                for chunk in [first_chunk, *rest_chunks]:
                    _normalize_chunk(chunk, resp_id, created, model_used)
                    yield f"data: {json.dumps(chunk)}\n\n"
                async for chunk in gen:
                    # Check for mid-stream errors
                    x_err_mid = chunk.get("x_error")
                    if x_err_mid:
                        yield f"data: {json.dumps({'error': {'message': x_err_mid, 'type': 'provider_error', 'code': '502'}})}\n\n"
                        yield "data: [DONE]\n\n"
                        return
                    _normalize_chunk(chunk, resp_id, created, model_used)
                    yield f"data: {json.dumps(chunk)}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(
                _stream(),
                media_type="text/event-stream",
                headers={
                    "X-Key-Provider": provider_used,
                    "X-Model-Used": model_used,
                    "X-Request-Id": resp_id,
                },
            )

        try:
            result, key_data = await dispatch_complete(
                rotator,
                capabilities=caps,
                messages=req.messages,
                subscriber_id=subscriber,
                min_context=min_context,
                require_tools=require_tools,
                require_vision=require_vision,
                **kwargs,
            )
        except Exception as exc:
            return _openai_error(
                502,
                f"{type(exc).__name__}: {str(exc)[:200]}",
                "dispatch_error",
            )

        if result.error and not result.text:
            if result.was_429:
                return _openai_error(429, result.error, "rate_limit_error")
            if "exhausted" in result.error.lower():
                return _openai_error(503, result.error, "server_error")
            if "connection" in result.error.lower() or "network" in result.error.lower():
                return _openai_error(502, result.error, "provider_error")
            return _openai_error(502, result.error, "provider_error")

        model_used = key_data["model"] if (rotator.force_provider and key_data) else (
            model_param if model_param not in ("auto", "default") else (key_data["model"] if key_data else "unknown")
        )
        provider_used = key_data["provider"] if key_data else "unknown"

        if req.unicid and key_data and key_data.get("is_sticky_enabled"):
            store.create_sticky_session(
                req.unicid,
                key_data["key_id"],
                key_data["provider"],
                key_data.get("model"),
                key_data.get("sticky_ttl_hours", 1),
            )

        prompt_tokens = _estimate_tokens(req.messages)
        completion_tokens = result.tokens_used
        total_tokens = prompt_tokens + completion_tokens

        msg_out: dict[str, Any] = {"role": "assistant", "content": result.text}
        if getattr(result, "reasoning_content", None):
            msg_out["reasoning_content"] = result.reasoning_content
        return {
            "id": resp_id,
            "object": "chat.completion",
            "created": created,
            "model": model_used,
            "choices": [{"index": 0, "message": msg_out, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
            "x_key_provider": provider_used,
        }

    @router.post("/v1/responses")
    async def responses_endpoint(
        req: ResponsesRequest,
        x_keypool_capabilities: Annotated[str | None, Header()] = None,
        x_subscriber_id: Annotated[str | None, Header()] = None,
    ) -> Any:
        from llm_keypool.core.model_parser import ModelParser

        caps = x_keypool_capabilities.split(",") if x_keypool_capabilities else ["general_purpose"]
        subscriber = x_subscriber_id or "responses"
        messages = to_chat_messages(req)
        tools = to_chat_tools(req.tools)

        model_param = req.model or "auto"
        _, model_filter, _ = ModelParser.parse(model_param)

        response_id = f"resp_{uuid.uuid4().hex}"
        last_error: str | None = None
        last_key_data: dict[str, Any] | None = None
        last_result = None

        for _attempt in range(MAX_RETRIES):
            try:
                result, key_data = await dispatch_complete(
                    rotator,
                    capabilities=caps,
                    messages=messages,
                    subscriber_id=subscriber,
                    tools=tools,
                    max_tokens=req.max_output_tokens,
                    temperature=req.temperature,
                    top_p=req.top_p,
                    min_context=model_filter.context_min,
                    require_tools=model_filter.tools,
                    require_vision=model_filter.vision,
                )
                if result.text:
                    last_result = result
                    last_key_data = key_data
                    break
                last_error = result.error
            except Exception as e:
                last_error = str(e)

        if not last_result or not last_result.text:
            msg = last_error or "All available keys exhausted"
            if "rate" in msg.lower():
                return _openai_error(429, msg, "rate_limit_error")
            return _openai_error(503, msg, "server_error")

        model_out = (last_key_data or {}).get("model") or "auto"
        return build_response_object(
            response_id=response_id,
            model=model_out,
            text=last_result.text,
            tool_calls=[],
            prompt_tokens=_estimate_tokens(messages),
            completion_tokens=last_result.tokens_used,
        )

    return router


__all__ = ["_create_chat_router"]
