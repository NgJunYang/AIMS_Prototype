"""The only module that talks to the Anthropic API.

Every call is content-addressed and cached to disk. In DEMO_MODE=offline no
network call is attempted at all: a cache miss raises immediately with a clear
message rather than hanging on a dead venue Wi-Fi connection.
"""

import hashlib
import json
from typing import Any

from anthropic import Anthropic

from app.config import ANTHROPIC_API_KEY, DEMO_MODE, LLM_CACHE_DIR


class OfflineCacheMiss(RuntimeError):
    """Raised when offline mode is on and the response is not cached."""


def cache_key(model: str, prompt: str, image_b64: str | None) -> str:
    digest = hashlib.sha256()
    digest.update(model.encode())
    digest.update(b"\x00")
    digest.update(prompt.encode())
    digest.update(b"\x00")
    if image_b64:
        # Hash the image rather than storing it in the key.
        digest.update(hashlib.sha256(image_b64.encode()).hexdigest().encode())
    return digest.hexdigest()[:32]


def read_cache(key: str) -> dict[str, Any] | None:
    path = LLM_CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_cache(key: str, payload: dict[str, Any]) -> None:
    LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (LLM_CACHE_DIR / f"{key}.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


def complete_json(
    model: str,
    prompt: str,
    schema: dict[str, Any],
    image_b64: str | None = None,
    image_media_type: str = "image/jpeg",
    max_tokens: int = 4096,
    *,
    images_b64: list[str] | None = None,
) -> dict[str, Any]:
    """Call Claude and return a JSON object matching `schema`.

    Uses a forced tool call so the response is structured JSON rather than
    prose that has to be parsed. No `temperature` is set: the model family
    used here rejects that parameter outright (400 invalid_request_error)
    rather than ignoring it, so passing one at all breaks every call.
    """
    if image_b64 and images_b64:
        raise ValueError("Use either one image or a document's pages, not both.")
    # Preserve every existing single-image cache key. Document imports include
    # ordered pages and the schema, so neither page order nor schema can collide.
    key = cache_key(model, prompt, image_b64) if images_b64 is None else cache_key(
        model, prompt, json.dumps({"pages": images_b64, "schema": schema,
                                  "media_type": image_media_type}, sort_keys=True)
    )

    cached = read_cache(key)
    if cached is not None:
        return cached

    if DEMO_MODE == "offline":
        raise OfflineCacheMiss(
            f"DEMO_MODE is offline and no cached response exists for key {key}. "
            f"Run once with DEMO_MODE=live to populate fixtures/llm_cache/."
        )

    content: list[dict[str, Any]] = []
    for number, page in enumerate(images_b64 or [], start=1):
        content.extend([
            {"type": "text", "text": f"Document page {number}"},
            {"type": "image", "source": {"type": "base64", "media_type": image_media_type, "data": page}},
        ])
    if image_b64:
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image_media_type,
                    "data": image_b64,
                },
            }
        )
    content.append({"type": "text", "text": prompt})

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        tools=[
            {
                "name": "respond",
                "description": "Return the structured result.",
                "input_schema": schema,
            }
        ],
        tool_choice={"type": "tool", "name": "respond"},
        messages=[{"role": "user", "content": content}],
    )

    if images_b64 is not None and response.stop_reason == "max_tokens":
        raise RuntimeError("Document extraction exceeded the response limit; use a smaller PDF.")
    for block in response.content:
        if block.type == "tool_use":
            payload = dict(block.input)
            if images_b64 is not None:
                for field in schema.get("required", []):
                    if field not in payload or (schema.get("properties", {}).get(field, {}).get("type") == "array" and not isinstance(payload[field], list)):
                        raise RuntimeError("Document extraction returned a malformed result; retry extraction.")
            write_cache(key, payload)
            return payload

    raise RuntimeError("model did not return a tool_use block")
