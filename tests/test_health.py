from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from llm_keypool.core.health import check_all_keys, check_key_health


@pytest.mark.asyncio
async def test_check_all_keys_empty():
    store = MagicMock()
    store.get_all_keys.return_value = []
    result = await check_all_keys(store)
    assert result is None


@pytest.mark.asyncio
async def test_check_all_keys_with_keys():
    store = MagicMock()
    store.get_all_keys.return_value = [
        {"id": 1, "provider": "groq", "api_key": "gsk_test", "is_active": 1},
    ]
    result = await check_all_keys(store)
    assert result is None


@pytest.mark.asyncio
async def test_check_key_health():
    store = MagicMock()
    key = {"id": 1, "provider": "groq", "api_key": "test", "is_active": 1}
    result = await check_key_health(store, key)
    assert result is not None
