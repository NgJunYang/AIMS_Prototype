import json
from types import SimpleNamespace

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


def test_document_pages_use_one_call_and_ordered_schema_aware_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "LLM_CACHE_DIR", tmp_path)
    monkeypatch.setattr(llm, "DEMO_MODE", "live")
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(stop_reason="tool_use", content=[SimpleNamespace(type="tool_use", input={"questions": []})])
    monkeypatch.setattr(llm, "Anthropic", lambda **kw: SimpleNamespace(messages=SimpleNamespace(create=create)))
    schema = {"type": "object", "properties": {"questions": {"type": "array"}}, "required": ["questions"]}
    for _ in range(2):
        assert llm.complete_json("model", "document", schema, images_b64=["page1", "page2"], image_media_type="image/png") == {"questions": []}
    assert len(calls) == 1
    content = calls[0]["messages"][0]["content"]
    assert [c["source"]["data"] for c in content if c["type"] == "image"] == ["page1", "page2"]
    assert [c["text"] for c in content if c["type"] == "text"][:2] == ["Document page 1", "Document page 2"]
    llm.complete_json("model", "document", schema, images_b64=["page2", "page1"])
    llm.complete_json("model", "document", {**schema, "description": "new schema"}, images_b64=["page1", "page2"])
    assert len(calls) == 3


@pytest.mark.parametrize("reason,payload", [("max_tokens", {"questions": []}), ("tool_use", {"questions": "invalid"})])
def test_truncated_or_malformed_documents_are_not_cached(tmp_path, monkeypatch, reason, payload):
    monkeypatch.setattr(llm, "LLM_CACHE_DIR", tmp_path)
    monkeypatch.setattr(llm, "DEMO_MODE", "live")
    monkeypatch.setattr(llm, "Anthropic", lambda **kw: SimpleNamespace(messages=SimpleNamespace(create=lambda **kw:
        SimpleNamespace(stop_reason=reason, content=[SimpleNamespace(type="tool_use", input=payload)]))))
    schema = {"type": "object", "properties": {"questions": {"type": "array"}}, "required": ["questions"]}
    error_type = llm.OutputTruncationError if reason == "max_tokens" else llm.MalformedStructuredResponse
    with pytest.raises(error_type):
        llm.complete_json("model", "prompt", schema, images_b64=["page"])
    assert list(tmp_path.glob("*.json")) == []


def test_partially_recoverable_document_is_returned_but_not_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "LLM_CACHE_DIR", tmp_path)
    monkeypatch.setattr(llm, "DEMO_MODE", "live")
    payload = {"answers": [{"label": "Q1", "source_pages": "bad"}]}
    monkeypatch.setattr(llm, "Anthropic", lambda **kw: SimpleNamespace(messages=SimpleNamespace(create=lambda **kw:
        SimpleNamespace(stop_reason="tool_use", content=[SimpleNamespace(type="tool_use", input=payload)]))))
    schema = {"type": "object", "properties": {"answers": {"type": "array"}}, "required": ["answers"]}
    assert llm.complete_json("model", "prompt", schema, images_b64=["page"],
                             response_validator=lambda value: False) == payload
    assert list(tmp_path.glob("*.json")) == []


def test_live_mode_replaces_an_old_partially_malformed_cache_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "LLM_CACHE_DIR", tmp_path)
    monkeypatch.setattr(llm, "DEMO_MODE", "live")
    schema = {"type": "object", "properties": {"answers": {"type": "array"}}, "required": ["answers"]}
    key = llm.cache_key("model", "prompt", json.dumps(
        {"pages": ["page"], "schema": schema, "media_type": "image/jpeg"}, sort_keys=True
    ))
    llm.write_cache(key, {"answers": [{"source_pages": "bad"}]})
    valid = {"answers": [{"source_pages": [1]}]}
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(stop_reason="tool_use", content=[SimpleNamespace(type="tool_use", input=valid)])
    monkeypatch.setattr(llm, "Anthropic", lambda **kw: SimpleNamespace(messages=SimpleNamespace(create=create)))
    validator = lambda value: isinstance(value["answers"][0]["source_pages"], list)
    assert llm.complete_json("model", "prompt", schema, images_b64=["page"],
                             response_validator=validator) == valid
    assert len(calls) == 1 and llm.read_cache(key) == valid


def test_document_extension_keeps_existing_single_image_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "LLM_CACHE_DIR", tmp_path)
    monkeypatch.setattr(llm, "DEMO_MODE", "offline")
    llm.write_cache(llm.cache_key("model", "old prompt", "image"), {"existing": True})
    assert llm.complete_json("model", "old prompt", {}, image_b64="image") == {"existing": True}
