"""OpenAI-compatible HTTP proxy for llm-keypool.

Re-exports :func:`make_app` from :mod:`llm_keypool.api.app` for backward
compatibility. All route logic has been extracted to ``api/routes/``.
"""

from llm_keypool.api.app import make_app, _load_provider_configs
from llm_keypool.providers.dispatch import complete

# Legacy symbols kept for test backward compatibility
_KEYPOOL_MODEL_ID = "LLM-Keypool"
_KEYPOOL_MODEL_OWNER = "llm-keypool"


def _mask_key(api_key: str) -> str:
    if len(api_key) <= 8:
        return "****" + api_key[-4:] if len(api_key) > 4 else "****"
    return api_key[:4] + "****" + api_key[-4:]


__all__ = ["make_app", "_KEYPOOL_MODEL_ID", "_KEYPOOL_MODEL_OWNER", "_mask_key"]
