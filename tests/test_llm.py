import json

import pytest

from app import llm


def test_cache_key_is_stable_for_identical_input():
    a = llm.cache_key("model-x", "prompt text", "image-bytes-hash")
    b = llm.cache_key("model-x", "prompt text", "image-bytes-hash")
    assert a == b


def test_cache_key_changes_when_any_input_changes():
    base = llm.cache_key("model-x", "prompt", None)
    assert base != llm.cache_key("model-y", "prompt", None)
    assert base != llm.cache_key("model-x", "different", None)
    assert base != llm.cache_key("model-x", "prompt", "img")


def test_cache_write_then_read(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "LLM_CACHE_DIR", tmp_path)
    key = "abc123"
    llm.write_cache(key, {"result": 42})
    assert llm.read_cache(key) == {"result": 42}


def test_cache_miss_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "LLM_CACHE_DIR", tmp_path)
    assert llm.read_cache("nothing-here") is None


def test_offline_mode_raises_a_clear_error_on_cache_miss(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "LLM_CACHE_DIR", tmp_path)
    monkeypatch.setattr(llm, "DEMO_MODE", "offline")
    with pytest.raises(llm.OfflineCacheMiss) as error:
        llm.complete_json(
            model="model-x", prompt="hello", schema={"type": "object"}, image_b64=None
        )
    assert "offline" in str(error.value).lower()
