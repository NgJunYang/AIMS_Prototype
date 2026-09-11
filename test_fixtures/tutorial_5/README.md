# Tutorial 5 — synthetic test fixtures

These PDFs contain only synthetic/fake student data. They are intended to be
committed to GitHub so all developers can reproduce the same manual/end-to-end
testing workflow. Keep the original PDFs unchanged.

| File | Purpose |
| --- | --- |
| [01_Professor_Tutorial_5_Questions.pdf](01_Professor_Tutorial_5_Questions.pdf) | Professor question sheet containing Q1–Q5. |
| [02_Professor_Tutorial_5_Model_Solutions_and_Rubrics.pdf](02_Professor_Tutorial_5_Model_Solutions_and_Rubrics.pdf) | Reference solutions and suggested marking rubrics. |
| [03_Student_Tutorial_5_Worked_Submission.pdf](03_Student_Tutorial_5_Worked_Submission.pdf) | Worked answers from fictional student **Alex Tan**, student ID **2500123**. |

## Intended answers and errors

| Question | Student working |
| --- | --- |
| Q1 | Intentionally correct. |
| Q2 | Intentionally correct. |
| Q3 | Intentionally omits the root `x = 0`. |
| Q4 | Intentionally omits the negative root `x = -7`. |
| Q5 | Uses an incorrect factorisation and consequently produces incorrect roots. |

## Manual test workflow

Set up a Tutorial 5 assignment containing Q1–Q5, using the professor PDFs as
references for the questions, model solutions and rubrics. Use the existing
manual/per-question workflow for each answer. Keep all five submissions linked
to the same assignment and confirmed identity: Alex Tan, `2500123`.

1. AI-mark each question separately and inspect the intended correct answers
   and errors listed above.
2. Override individual rubric criterion scores; check that the AI suggestion
   remains distinguishable from the instructor's final score.
3. Edit **What went well**, **What needs attention**, and **How to improve**.
4. Mark each question as reviewed, saving the confirmed identity and feedback.
5. Check review progress across Q1–Q5. As an intermediate checkpoint, review
   only Q1–Q3 and verify that progress is **3 / 5**.
6. Verify that publication is prevented while any required question is missing,
   unmarked or unreviewed, and that the student cannot access these results.
7. Once all five questions have marks, feedback and explicit review, click
   **Publish Tutorial Results** to release the complete tutorial together.
8. Verify that the student can access every question's final professor-approved
   marks and edited feedback.

Also check that changing an assessment after review requires reviewing that
question again, and that **Unpublish Tutorial Results** hides all five results.

These files do not imply support for automatic whole-PDF question splitting.
They are reusable manual/end-to-end test data today. When whole-tutorial
ingestion is implemented later, reuse them to test automatic question detection
and student-answer splitting.

Keep runtime uploads, caches, generated API responses, `.env` files, real student
submissions and secrets out of Git; only these synthetic source PDFs and this
README belong in this fixture folder.
