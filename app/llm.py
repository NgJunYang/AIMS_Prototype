"""The only module that talks to the Anthropic API.

Every call is content-addressed and cached to disk. In DEMO_MODE=offline no
network call is attempted at all: a cache miss raises immediately with a clear
message rather than hanging on a dead venue Wi-Fi connection.
"""

import hashlib
import json
import logging
from collections.abc import Callable, Mapping
from typing import Any

from anthropic import Anthropic

from app.config import ANTHROPIC_API_KEY, DEMO_MODE, LLM_CACHE_DIR


logger = logging.getLogger(__name__)


class OfflineCacheMiss(RuntimeError):
    """Raised when offline mode is on and the response is not cached."""


class StructuredOutputError(RuntimeError):
    """A safe, classified failure in a model's structured response."""

    category = "malformed structured response"
    safe_message = "Document extraction returned a malformed structured response. No data was saved."


class MalformedStructuredResponse(StructuredOutputError):
    """The model did not return the required tool/object shape."""


class StructuredSchemaValidationError(StructuredOutputError):
    """The tool payload was JSON, but did not satisfy the application schema."""

    category = "schema validation failure"
    safe_message = "Document extraction failed structured-output schema validation. No data was saved."


class OutputTruncationError(StructuredOutputError):
    """The provider stopped before the structured response was complete."""

    category = "output truncation"
    safe_message = "Document extraction output was truncated at the model response limit. No data was saved."


ResponseValidator = Callable[[dict[str, Any]], bool]


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
    response_validator: ResponseValidator | None = None,
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
        # Older cache entries predate document-level Pydantic validation. Do
        # not let one bad entry permanently poison live retries. In offline
        # mode it is still useful to return a partially recoverable entry; the
        # caller's validator decides whether it is safe to do so.
        try:
            cacheable = response_validator(cached) if response_validator is not None else True
            if cacheable or DEMO_MODE == "offline":
                return cached
            logger.warning("Ignoring partially malformed structured cache entry %s", key)
        except StructuredOutputError:
            if DEMO_MODE == "offline":
                raise OfflineCacheMiss(
                    f"DEMO_MODE is offline and cached response {key} is invalid. "
                    "Run once with DEMO_MODE=live to replace it."
                )
            logger.warning("Ignoring invalid structured cache entry %s", key)

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

    if response.stop_reason == "max_tokens":
        raise OutputTruncationError("Provider stop_reason was max_tokens.")
    for block in response.content:
        if block.type == "tool_use":
            if not isinstance(block.input, Mapping):
                raise MalformedStructuredResponse("Tool input was not a JSON object.")
            payload = dict(block.input)
            if images_b64 is not None:
                for field in schema.get("required", []):
                    if field not in payload:
                        raise MalformedStructuredResponse(
                            f"Required top-level field {field!r} was missing."
                        )
                    if schema.get("properties", {}).get(field, {}).get("type") == "array" and not isinstance(payload[field], list):
                        raise MalformedStructuredResponse(
                            f"Required top-level field {field!r} was {type(payload[field]).__name__}, not an array."
                        )
            cacheable = response_validator(payload) if response_validator is not None else True
            if cacheable:
                write_cache(key, payload)
            else:
                # The caller can safely salvage part of this response, but a
                # future extraction must get a fresh chance at a fully valid
                # result rather than inheriting the malformed block forever.
                logger.warning("Structured response %s was partially recoverable and was not cached", key)
            return payload

    raise MalformedStructuredResponse(
        f"Model response contained no tool_use block (stop_reason={response.stop_reason!r})."
    )
