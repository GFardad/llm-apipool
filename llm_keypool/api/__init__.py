"""FastAPI application package for llm-keypool.

Provides the OpenAI-compatible proxy API with all routes organized
into separate modules following the FreeLLMAPI architecture.
"""

from llm_keypool.api.app import make_app

__all__ = ["make_app"]
