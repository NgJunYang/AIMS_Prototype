from app.models import Step
from app.practice import TEMPLATES
from app.store import all_misconceptions, list_questions
from app.verifier import solution_set, verify


def test_every_model_solution_line_parses():
    for question in list_questions():
        for latex in question.model_solution_steps:
            assert solution_set(latex, question.variable) is not None, (
                f"{question.id}: unparseable model line {latex!r}"
            )


def test_every_model_solution_verifies_as_correct_against_itself():
    for question in list_questions():
        steps = [
            Step(index=i, latex=text)
            for i, text in enumerate(question.model_solution_steps, start=1)
        ]
        report = verify(steps, question.model_solution_steps, question.variable)
        assert report.final_answer_correct, f"{question.id} does not verify against itself"
        assert report.first_divergence_index is None, (
            f"{question.id} has a divergence in its own model solution "
            f"at step {report.first_divergence_index}"
        )


def test_misconception_practice_mapping_matches_the_templates():
    """`practice_template_ids` in the seed JSON documents the tag -> template
    mapping that `TEMPLATES` implements. Nothing reads the JSON copy at
    runtime, so without this test the two could drift silently and the
    documentation would quietly become a lie.
    """
    from_templates: dict[str, set[str]] = {}
    for template in TEMPLATES.values():
        for tag in template.misconception_tags:
            from_templates.setdefault(tag, set()).add(template.id)

    for tag, entry in all_misconceptions().items():
        assert set(entry["practice_template_ids"]) == from_templates.get(tag, set()), (
            f"{tag}: misconceptions.json says {entry['practice_template_ids']} "
            f"but TEMPLATES says {sorted(from_templates.get(tag, set()))}"
        )

    # And no template targets a tag the catalogue has never heard of.
    assert set(from_templates) <= set(all_misconceptions())
