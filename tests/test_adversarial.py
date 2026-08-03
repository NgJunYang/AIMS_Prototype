"""Robustness / adversarial tests.

The goal is not coverage theatre. `app/verifier.py` is the only component
permitted to assert mathematical truth, and the worst possible failure mode is
not a crash -- it is a wrong-but-plausible solution set that gets handed to the
marking model as GROUND TRUTH and fabricates a misconception against a student
who made no error. Six such bugs were already found and fixed (see the
`test_bug*` tests in tests/test_verifier.py); every test below exists to prove
the system *degrades* (returns None / flags unparseable / refuses to guess)
rather than *fabricates* when it is fed garbage, adversarial, or malformed
input.

Where a case only proves "no exception", that is explicitly the weaker half of
the contract, so the majority of these tests additionally assert that no
solution set, no divergence and no misconception was invented.
"""

import pytest
from fastapi.testclient import TestClient

from app import main, marker, store
from app.main import app
from app.models import MarkProposal, Step, VerificationReport
from app.verifier import solution_set, verify

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolate_disk_writes(tmp_path, monkeypatch):
    """Same isolation as tests/test_api.py: never touch fixtures/ or data/."""
    images = tmp_path / "images"
    submissions = tmp_path / "submissions"
    images.mkdir()
    submissions.mkdir()
    monkeypatch.setattr(main, "IMAGES_DIR", images)
    monkeypatch.setattr(store, "SUBMISSIONS_DIR", submissions)


def steps(*latex: str) -> list[Step]:
    return [Step(index=i, latex=text) for i, text in enumerate(latex, start=1)]


# ---------------------------------------------------------------------------
# 1. Pure garbage strings must degrade to None, never raise, never a guess.
# ---------------------------------------------------------------------------

GARBAGE_STRINGS = [
    "",
    "   ",
    "???",
    r"\frac{",
    "=",
    "\\\\",
    "$$$",
    "x^^2",
    "(((",
    "x" * 5000,
]


@pytest.mark.parametrize("garbage", GARBAGE_STRINGS, ids=lambda s: repr(s[:20]))
def test_garbage_strings_degrade_to_none_without_raising(garbage):
    # "x^^2" is the interesting one here: sympy's parse_latex does not raise on
    # a malformed exponent, it silently truncates and hands back the bare
    # symbol 'x' (parse_latex('x^^2') -> Symbol('x')), which would otherwise
    # become Eq(x, 0) -> {'0'} -- exactly the fabricated-lost-root shape this
    # suite exists to prevent. app/latex_utils.py now calls parse_latex(...,
    # strict=True), which raises LaTeXParsingError on all of these instead of
    # guessing; _parse_single's except Exception then degrades to None. See
    # the fix note in the report for the other silent-truncation cases this
    # closed off (x**2, 'x + ', 'x)', 'x(' all used to truncate to Symbol('x')
    # the same way).
    assert solution_set(garbage, "x") is None


# ---------------------------------------------------------------------------
# 2. A chain made entirely of unparseable lines.
# ---------------------------------------------------------------------------


def test_a_chain_of_only_unparseable_lines_yields_no_fabricated_verdict():
    report = verify(
        steps("???", r"\frac{", "x^^2", "((("),
        model_solution_steps=["x = 1"],
        variable="x",
    )
    assert report.candidate_misconceptions == []
    assert report.final_answer_correct is False
    assert report.final_answer_verified is False
    assert len(report.steps) == 4
    for verification in report.steps:
        assert verification.parsed is False
        assert verification.divergence == "unparseable"
        assert verification.solutions == []


# ---------------------------------------------------------------------------
# 3. Wrong variable.
# ---------------------------------------------------------------------------


def test_a_line_in_the_wrong_variable_is_unparseable_not_a_guess():
    # 'y = 2' has no 'x' in it at all, so the free-symbol guard in
    # _parse_single rejects it (free_symbols == {y} != {x}) rather than
    # silently reporting the empty set, which would read downstream as
    # "every root of x was lost".
    assert solution_set("y = 2", variable="x") is None


# ---------------------------------------------------------------------------
# 4. A cubic and a plain linear equation -- document actual behaviour.
# ---------------------------------------------------------------------------


def test_a_cubic_is_solved_but_the_project_only_targets_quadratics():
    # The verifier itself is not restricted to quadratics -- sympy.solve
    # handles this cubic fine and returns all three integer roots. The
    # rubric/seed data (app/seeds/questions.json) only ever poses quadratics;
    # nothing in verifier.py enforces that boundary, so this is current,
    # intentional behaviour rather than a gap. Documented here so a future
    # change to that boundary has a pinned test to update.
    result = solution_set("x^3 - 6x^2 + 11x - 6 = 0", "x")
    assert result == {"1", "2", "3"}


def test_a_plain_linear_equation_solves_to_a_single_root():
    assert solution_set("2x = 4", "x") == {"2"}


# ---------------------------------------------------------------------------
# 5. Out-of-order / duplicate step indices.
# ---------------------------------------------------------------------------


def test_out_of_order_indices_do_not_raise():
    student_steps = [
        Step(index=5, latex="x^2 - 5x + 6 = 0"),
        Step(index=1, latex="(x - 2)(x - 3) = 0"),
        Step(index=3, latex="x = 2, x = 3"),
    ]
    report = verify(student_steps, model_solution_steps=["x = 2, x = 3"], variable="x")
    assert [v.index for v in report.steps] == [5, 1, 3]


def test_duplicate_indices_do_not_raise():
    student_steps = [
        Step(index=1, latex="x^2 - 5x + 6 = 0"),
        Step(index=1, latex="(x - 2)(x - 3) = 0"),
        Step(index=1, latex="x = 2, x = 3"),
    ]
    report = verify(student_steps, model_solution_steps=["x = 2, x = 3"], variable="x")
    assert len(report.steps) == 3
    # classify() looks up `by_index.get(verification.index - 1)` to find the
    # previous step's text; with duplicate indices this is ambiguous but must
    # not raise -- it just may not find a sensible previous line.
    assert report.final_answer_verified in (True, False)


# ---------------------------------------------------------------------------
# 6. A very long chain.
# ---------------------------------------------------------------------------


def test_a_very_long_chain_completes_without_raising():
    student_steps = steps(*([r"x = 2, x = 3"] * 50))
    report = verify(student_steps, model_solution_steps=["x = 2, x = 3"], variable="x")
    assert len(report.steps) == 50
    assert report.final_answer_correct is True
    assert report.candidate_misconceptions == []


# ---------------------------------------------------------------------------
# 7. Prose-like inputs containing the unknown -- the exact bug-2 shape.
# ---------------------------------------------------------------------------

PROSE_LIKE_INPUTS = [
    "expand",
    "factorise the expression",
    "take out a factor of x",
    r"\text{expand the brackets}",
    r"\text{factorise the expression}",
    r"\textbf{expand}",
    r"\textbf{take out a factor of x}",
]


@pytest.mark.parametrize("prose", PROSE_LIKE_INPUTS)
def test_prose_containing_the_unknown_never_produces_a_solution_set(prose):
    # This is the exact bug class that fabricated the headline misconception:
    # parse_latex happily reads bare prose as a product of single-letter
    # symbols ('expand' -> e*x*p*a*n*d), and if that product's only free
    # symbol happened to coincide with the unknown, it would parse as a "real"
    # equation. It must instead be None: not mathematics, not to be judged.
    assert solution_set(prose, "x") is None, prose


def test_prose_in_a_chain_degrades_and_invents_no_misconception():
    report = verify(
        steps("x^2 - 5x + 6 = 0", "factorise the expression", "x = 2, x = 3"),
        model_solution_steps=["x^2 - 5x + 6 = 0", "x = 2, x = 3"],
        variable="x",
    )
    assert report.steps[1].parsed is False
    assert report.candidate_misconceptions == []
    assert report.final_answer_correct is True


# ---------------------------------------------------------------------------
# 8. Non-equality relations.
# ---------------------------------------------------------------------------

NON_EQUALITY_TOKENS = [
    r"\to",
    r"\rightarrow",
    r"\longrightarrow",
    r"\geq",
    r"\leq",
    r"\neq",
    r"\approx",
    "<",
    ">",
]


@pytest.mark.parametrize("token", NON_EQUALITY_TOKENS)
def test_non_equality_relations_are_unparseable_not_solved(token):
    # sympy's parse_latex does not fail on most of these -- it *silently
    # truncates* at the token it does not recognise ('x \to 2' parses as the
    # bare expression 'x', which becomes Eq(x, 0) -> {'0'}, the single most
    # dangerous fabricated value since classify() reads "0" in lost_roots as
    # the headline 'divided_by_variable_lost_root' misconception). That is why
    # app/latex_utils.py rejects any non-equality relation with a *pre-parse*
    # regex (_NON_EQUALITY_RELATION) rather than trusting parse_latex to fail
    # loudly. '\geq'/'\leq' etc. do parse (to Relational objects) rather than
    # truncate, and are caught by a second, in-parser guard on the operand
    # type. Either way the outcome must be None.
    assert solution_set(f"x {token} 2", "x") is None, token


def test_an_inequality_in_a_chain_degrades_and_accuses_nobody():
    report = verify(
        steps("x^2 - 5x + 6 = 0", r"x \geq 2", "x = 2, x = 3"),
        model_solution_steps=["x^2 - 5x + 6 = 0", "x = 2, x = 3"],
        variable="x",
    )
    assert report.steps[1].parsed is False
    assert report.candidate_misconceptions == []
    assert report.final_answer_correct is True


# ---------------------------------------------------------------------------
# 9. Marker robustness against a malformed model response.
# ---------------------------------------------------------------------------


def _empty_report() -> VerificationReport:
    return VerificationReport(steps=[], final_answer_correct=False, candidate_misconceptions=[])


def _assert_valid_proposal(proposal: MarkProposal, question) -> None:
    assert isinstance(proposal, MarkProposal)
    returned_ids = {c.criterion_id for c in proposal.criteria}
    assert returned_ids == {c.id for c in question.criteria}
    for criterion in proposal.criteria:
        assert 0 <= criterion.proposed <= criterion.max


MALFORMED_MARKER_RESPONSES = [
    {},
    {"criteria": [], "misconceptions": []},
    {
        "criteria": [{"criterion_id": "NOT_A_REAL_CRITERION", "proposed": 1, "justification": "x"}],
        "misconceptions": [],
    },
    {
        "criteria": [{"criterion_id": "C1", "proposed": "a lot", "justification": "x"}],
        "misconceptions": [],
    },
    {
        "criteria": [{"criterion_id": "C1", "proposed": -7, "justification": "x"}],
        "misconceptions": [],
    },
    {
        "criteria": [{"criterion_id": "C1", "proposed": 10_000, "justification": "x"}],
        "misconceptions": [],
    },
    # Beyond the required matrix: wrong *types* for whole fields, not just
    # values. Found while writing this suite -- see the report.
    {"criteria": "not-a-list", "misconceptions": "also-not-a-list"},
    {"criteria": ["not-a-dict-either"], "misconceptions": [1, 2, "ok"]},
]


@pytest.mark.parametrize(
    "fake_response", MALFORMED_MARKER_RESPONSES, ids=range(len(MALFORMED_MARKER_RESPONSES))
)
def test_mark_degrades_gracefully_on_a_malformed_model_response(monkeypatch, fake_response):
    monkeypatch.setattr(marker, "complete_json", lambda **kwargs: fake_response)
    question = store.get_question("q2")
    proposal = marker.mark(question, [], _empty_report())
    _assert_valid_proposal(proposal, question)


# ---------------------------------------------------------------------------
# 10. API robustness: malformed bodies and missing fields never 5xx.
# ---------------------------------------------------------------------------


def test_non_json_body_on_create_submission_is_a_4xx_not_a_5xx():
    response = client.post(
        "/api/submissions",
        content="{not valid json",
        headers={"content-type": "application/json"},
    )
    assert 400 <= response.status_code < 500


def test_missing_required_field_on_create_submission_is_422():
    response = client.post("/api/submissions", json={})
    assert response.status_code == 422


def test_wrong_type_for_a_field_is_422_not_500():
    response = client.post("/api/submissions", json={"question_id": 12345})
    assert response.status_code == 422


def test_non_json_body_on_put_steps_is_a_4xx_not_a_5xx():
    response = client.put(
        "/api/submissions/whatever/steps",
        content="not json at all",
        headers={"content-type": "application/json"},
    )
    assert 400 <= response.status_code < 500


def test_missing_field_on_override_is_422():
    response = client.post(
        "/api/submissions/whatever/override", json={"criterion_id": "C1"}
    )
    assert response.status_code == 422


def test_malformed_step_shape_on_put_steps_is_422():
    response = client.put(
        "/api/submissions/whatever/steps",
        json={"steps": [{"index": "not-an-int", "latex": "x = 2"}]},
    )
    assert response.status_code == 422


def test_transcribe_with_no_file_is_a_4xx_not_a_5xx():
    submission_id = client.post(
        "/api/submissions", json={"question_id": "q2"}
    ).json()["id"]
    response = client.post(f"/api/submissions/{submission_id}/transcribe")
    assert 400 <= response.status_code < 500


# ---------------------------------------------------------------------------
# 11. PUT /steps with an empty list clears downstream state.
# ---------------------------------------------------------------------------


def test_put_empty_steps_is_ok_and_clears_downstream(monkeypatch):
    submission_id = client.post("/api/submissions", json={"question_id": "q2"}).json()["id"]
    client.put(
        f"/api/submissions/{submission_id}/steps",
        json={"steps": [{"index": 1, "latex": "x^2 = 5x"}]},
    )
    client.post(f"/api/submissions/{submission_id}/verify")

    response = client.put(f"/api/submissions/{submission_id}/steps", json={"steps": []})
    assert response.status_code == 200
    body = response.json()
    assert body["confirmed_steps"] == []
    assert body["verification"] is None
    assert body["marks"] is None
    assert body["feedback"] is None
    assert body["practice"] == []


# ---------------------------------------------------------------------------
# 12. Path traversal in a submission id.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "traversal_id",
    [
        "..%2F..%2Fetc%2Fpasswd",
        "../../etc/passwd",
        "....//....//etc/passwd",
        "..\\..\\windows\\win.ini",
    ],
)
def test_path_traversal_in_submission_id_does_not_escape_the_submissions_dir(
    traversal_id, tmp_path
):
    # store.load_submission builds SUBMISSIONS_DIR / f"{submission_id}.json".
    # A slash in the id never reaches routing at all (FastAPI's default path
    # converter does not match "/" inside a plain {submission_id} segment, so
    # an encoded slash 404s before this module even sees the id); a raw ".."
    # with no slash just becomes a harmless literal filename ("...json").
    # Plant a real secret one level above the (isolated, per-test) submissions
    # directory and confirm it is never read and never leaks into the
    # response, whatever status code comes back.
    secret = tmp_path / "secret.json"
    secret.write_text('{"leaked": true}', encoding="utf-8")

    response = client.get(f"/api/submissions/{traversal_id}")
    assert 400 <= response.status_code < 500
    assert "leaked" not in response.text
