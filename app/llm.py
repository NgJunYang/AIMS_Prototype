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
) -> dict[str, Any]:
    """Call Claude and return a JSON object matching `schema`.

    Uses a forced tool call so the response is structured JSON rather than
    prose that has to be parsed. No `temperature` is set: the model family
    used here rejects that parameter outright (400 invalid_request_error)
    rather than ignoring it, so passing one at all breaks every call.
    """
    key = cache_key(model, prompt, image_b64)

    cached = read_cache(key)
    if cached is not None:
        return cached

    if DEMO_MODE == "offline":
        raise OfflineCacheMiss(
            f"DEMO_MODE is offline and no cached response exists for key {key}. "
            f"Run once with DEMO_MODE=live to populate fixtures/llm_cache/."
        )

    content: list[dict[str, Any]] = []
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

    for block in response.content:
        if block.type == "tool_use":
            payload = dict(block.input)
            write_cache(key, payload)
            return payload

    raise RuntimeError("model did not return a tool_use block")
