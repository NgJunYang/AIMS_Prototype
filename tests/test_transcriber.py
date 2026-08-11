import hashlib

from app import transcriber
from app.models import IdentityExtraction, Transcription

# The student prompt is hashed into llm.cache_key, so a one-character edit
# invalidates every warmed transcription and turns the offline photo demo into
# a 503. If this test fails you have changed the prompt: that may be correct,
# but the cache must then be re-warmed and this hash updated deliberately.
#
# Updated deliberately: the student prompt now also asks the model to read a
# name/student id off the page (see _STUDENT_FRAMING). The lecturer-page
# prompt, and its cache key, are untouched.
STUDENT_PROMPT_SHA256 = (
    "3bbe14236b77214c17da05c50437d25ecb3113448735914c55000ad905e28608"
)


def test_the_student_prompt_is_unchanged_byte_for_byte():
    actual = hashlib.sha256(transcriber.build_prompt().encode()).hexdigest()
    assert actual == STUDENT_PROMPT_SHA256


def test_the_lecturer_prompt_is_not_framed_as_a_student_page():
    assert "student" not in transcriber.build_prompt("model_solution").lower()


def test_the_lecturer_prompt_still_forbids_correcting():
    """Faithful transcription matters more on the lecturer's page, not less:
    an error the model silently repairs is one SymPy can no longer catch."""
    lowered = transcriber.build_prompt("model_solution").lower()
    assert "do not solve" in lowered
    assert "do not correct" in lowered
    assert "including any mathematical errors" in lowered


def test_the_lecturer_prompt_never_asserts_the_page_is_correct():
    """An authority cue is exactly what makes a vision model tidy up an
    inconsistency instead of reporting it."""
    lowered = transcriber.build_prompt("model_solution").lower()
    assert "not authoritative" in lowered
    assert "is authoritative" not in lowered
    assert "expert" not in lowered


def test_both_prompts_share_the_same_fidelity_rules():
    """One shared constant, so the rules cannot drift apart invisibly."""
    for source in ("student", "model_solution"):
        assert transcriber._FIDELITY_RULES in transcriber.build_prompt(source)


def test_the_two_prompts_actually_differ():
    """Otherwise the feature is a no-op that still costs a second cache entry."""
    assert transcriber.build_prompt() != transcriber.build_prompt("model_solution")


def _capture_prompt(monkeypatch) -> dict:
    captured: dict = {}

    def fake(**kwargs):
        captured.update(kwargs)
        return {"steps": [{"latex": "x = 1", "confidence": "high"}], "notes": ""}

    monkeypatch.setattr(transcriber, "complete_json", fake)
    return captured


def test_transcribe_still_sends_the_student_prompt(monkeypatch):
    captured = _capture_prompt(monkeypatch)
    transcriber.transcribe(image_b64="fake")
    assert captured["prompt"] == transcriber.build_prompt("student")


def test_transcribe_model_solution_sends_the_lecturer_prompt(monkeypatch):
    """Without this, a wiring slip silently reverts to the student framing."""
    captured = _capture_prompt(monkeypatch)
    transcriber.transcribe_model_solution(image_b64="fake")
    assert captured["prompt"] == transcriber.build_prompt("model_solution")
    assert "student" not in captured["prompt"].lower()


def test_transcribe_model_solution_parses_and_reindexes(monkeypatch):
    fake = {
        "steps": [
            {"latex": "x^2 - 7x + 12 = 0", "confidence": "high"},
            {"latex": "  ", "confidence": "high"},
            {"latex": "x = 3, x = 4", "confidence": "low"},
        ],
        "notes": "margin note ignored",
    }
    monkeypatch.setattr(transcriber, "complete_json", lambda **kwargs: fake)

    result = transcriber.transcribe_model_solution(image_b64="fake")

    assert [s.index for s in result.steps] == [1, 2]
    assert result.steps[1].confidence == "low"
    assert result.notes == "margin note ignored"


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
        "student_name": "Jamie Lee",
        "student_id": "A1234567",
        "identity_confidence": "high",
    }
    monkeypatch.setattr(transcriber, "complete_json", lambda **kwargs: fake)

    result, identity = transcriber.transcribe(image_b64="fake", media_type="image/jpeg")

    assert isinstance(result, Transcription)
    assert [s.index for s in result.steps] == [1, 2]
    assert result.steps[1].confidence == "low"
    assert result.notes == "second line is faint"
    assert isinstance(identity, IdentityExtraction)
    assert identity.name == "Jamie Lee"
    assert identity.student_id == "A1234567"
    assert identity.confidence == "high"


def test_transcribe_drops_empty_lines(monkeypatch):
    fake = {
        "steps": [{"latex": "  ", "confidence": "high"}, {"latex": "x = 1"}],
        "notes": "",
        "student_name": None,
        "student_id": None,
        "identity_confidence": "low",
    }
    monkeypatch.setattr(transcriber, "complete_json", lambda **kwargs: fake)

    result, identity = transcriber.transcribe(image_b64="fake", media_type="image/jpeg")

    assert len(result.steps) == 1
    assert result.steps[0].index == 1


def test_transcribe_never_fabricates_an_absent_identity(monkeypatch):
    """Degrade-not-fabricate, the same standard applied to a mistranscribed
    step: no name/id visible must come back null, never guessed - a wrong
    name misattributes someone else's grade."""
    fake = {
        "steps": [{"latex": "x = 1", "confidence": "high"}],
        "notes": "",
        "student_name": None,
        "student_id": None,
        "identity_confidence": "low",
    }
    monkeypatch.setattr(transcriber, "complete_json", lambda **kwargs: fake)

    _, identity = transcriber.transcribe(image_b64="fake", media_type="image/jpeg")

    assert identity.name is None
    assert identity.student_id is None
    assert identity.confidence == "low"


def test_transcribe_treats_blank_identity_strings_as_absent(monkeypatch):
    """A model that answers "" instead of null must not save an empty-string
    name over the lecturer's typed one or the "Student N" fallback."""
    fake = {
        "steps": [{"latex": "x = 1", "confidence": "high"}],
        "notes": "",
        "student_name": "",
        "student_id": "",
        "identity_confidence": "low",
    }
    monkeypatch.setattr(transcriber, "complete_json", lambda **kwargs: fake)

    _, identity = transcriber.transcribe(image_b64="fake", media_type="image/jpeg")

    assert identity.name is None
    assert identity.student_id is None


def test_transcribe_model_solution_return_type_is_unchanged(monkeypatch):
    """No identity extraction on a lecturer's own page - still a bare
    Transcription, not a tuple, so every existing caller keeps working."""
    fake = {"steps": [{"latex": "x = 1", "confidence": "high"}], "notes": ""}
    monkeypatch.setattr(transcriber, "complete_json", lambda **kwargs: fake)

    result = transcriber.transcribe_model_solution(image_b64="fake")

    assert isinstance(result, Transcription)
