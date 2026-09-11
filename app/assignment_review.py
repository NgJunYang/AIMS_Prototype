"""Assignment review grouping and completeness checks, without file I/O."""

from app.models import Assignment, AssignmentQuestionReview, AssignmentReviewStatus, Submission


def is_assignment_tutorial(submission: Submission) -> bool:
    return submission.channel == "tutorial" and submission.assignment_id is not None


def student_key(submission: Submission) -> tuple[str, str]:
    student_id = (submission.student_id or "").strip().casefold()
    if student_id:
        return "id", student_id
    return "name", " ".join(submission.student_pseudonym.split()).casefold()


def student_submissions(anchor: Submission, submissions: list[Submission]) -> list[Submission]:
    # Never merge a missing-ID script into an identified student by name alone.
    # Two students may share a name; the instructor can confirm the missing ID.
    return [s for s in submissions
            if s.assignment_id == anchor.assignment_id and student_key(s) == student_key(anchor)]


def review_status(anchor: Submission, assignment: Assignment,
                  submissions: list[Submission]) -> AssignmentReviewStatus:
    group = student_submissions(anchor, submissions)
    questions = []
    for question_id in assignment.question_ids:
        matches = [s for s in group if s.question_id == question_id]
        row = AssignmentQuestionReview(question_id=question_id)
        if not matches:
            row.problems = ["missing submission"]
        elif len(matches) > 1:
            row.problems = ["multiple submissions; resolve the duplicate student/question association"]
        else:
            submission = matches[0]
            row.submission_id = submission.id
            row.marked = submission.marks is not None
            row.has_feedback = submission.feedback is not None
            row.reviewed = submission.reviewed and row.marked and row.has_feedback
            row.published = submission.published
            if not row.marked:
                row.problems.append("not marked")
            if not row.has_feedback:
                row.problems.append("missing feedback")
            if not submission.reviewed:
                row.problems.append("not reviewed")
        questions.append(row)
    ready = bool(questions) and all(not row.problems for row in questions)
    return AssignmentReviewStatus(
        assignment_id=assignment.id, assignment_title=assignment.title,
        student_pseudonym=anchor.student_pseudonym, student_id=anchor.student_id,
        total_questions=len(questions), reviewed_count=sum(row.reviewed for row in questions),
        ready_to_publish=ready, published=ready and all(row.published for row in questions),
        questions=questions,
    )
