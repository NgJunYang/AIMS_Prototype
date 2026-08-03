from app import transcriber
from app.models import Transcription


def test_prompt_never_mentions_the_answer_or_the_model_solution():
    prompt = transcriber.build_prompt()
    lowered = prompt.lower()
    assert "model solution" not in lowered
    assert "correct answer" not in lowered
    assert "solve" in lowered  # it should explicitly say NOT to solve
    assert "do not solve" in lowered


def test_transcribe_parses_a_cached_response(monkeypatch):
    fake = {
        "steps": [
            {"latex": "x^2 = 5x", "confidence": "high"},
            {"latex": "x = 5", "confidence": "low"},
        ],
        "notes": "second line is faint",
    }
    monkeypatch.setattr(transcriber, "complete_json", lambda **kwargs: fake)

    result = transcriber.transcribe(image_b64="fake", media_type="image/jpeg")

    assert isinstance(result, Transcription)
    assert [s.index for s in result.steps] == [1, 2]
    assert result.steps[1].confidence == "low"
    assert result.notes == "second line is faint"


def test_transcribe_drops_empty_lines(monkeypatch):
    fake = {"steps": [{"latex": "  ", "confidence": "high"}, {"latex": "x = 1"}], "notes": ""}
    monkeypatch.setattr(transcriber, "complete_json", lambda **kwargs: fake)

    result = transcriber.transcribe(image_b64="fake", media_type="image/jpeg")

    assert len(result.steps) == 1
    assert result.steps[0].index == 1
