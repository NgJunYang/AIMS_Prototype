# Whole-tutorial PDF ingestion

In **Assignments**, create a **Tutorial** with no selected bank questions. Open
its **Whole tutorial PDF import** section:

1. **Upload Question Paper PDF**. Inspect the original pages; edit labels,
   prompts, variable and topic, add/delete false or missing detections, and
   reorder questions. **Confirm Questions** saves an import draft, not usable
   question-bank entries.
2. **Upload Model Solutions PDF**. Inspect each mapping and transcription. Edit
   the master rubric and correct any mathematical validation errors. Check the
   confirmation box for every block, then **Confirm Solutions & Rubrics**.
   Only validated questions are saved to the bank and attached to the assignment,
   in confirmed order. Labels such as Q2(a) are distinct from globally unique
   bank IDs. Existing individual question/rubric editors remain available.
3. **Upload Completed Tutorial PDF**. Confirm the student's name/ID and each
   answer's question mapping, source pages and working. Delete extra blocks,
   add missing blocks, or explicitly confirm an unanswered question with no
   working lines. **Confirm & Start Marking** creates normal individual
   submissions and then runs the existing marking endpoint for each question.
4. **Open Instructor Review** uses the existing Workbench. Review source pages,
   edit scores/feedback, mark each question reviewed, and finally publish the
   complete tutorial using **Publish Tutorial Results**. Import confirmation is
   not marking review and never grants student access.

The synthetic files in `test_fixtures/tutorial_5/` exercise this full sequence.
Use the three numbered PDFs in order and confirm Alex Tan / `2500123` as the
student. Their contents are unchanged. Existing manual/per-question uploads
also continue to work.

## Architecture and validation

- `uploads.render_document` renders every page through the existing PyMuPDF/PNG
  renderer. Questions and answers can share pages or span multiple pages; there
  is no page-to-question assumption and no bounding-box cropping.
- `tutorial_ingestion` uses one structured Claude tool response per uploaded
  document. It receives numbered page images and confirmed prompt/label context.
  Student extraction never receives model answers or rubrics and is instructed
  to preserve mistakes rather than solve or repair working.
- Matching prioritizes normalized explicit labels, including Q1, Question 1,
  1., 1), Q2(a), 2(a), 2b and a contextual Part (a). Context/semantic fallbacks
  are flagged for review. Unmatched extras remain editable; missing questions
  get empty blocks. Duplicate mappings cannot be confirmed.
- Pydantic import schemas validate structured output. One invalid item becomes
  a flagged placeholder while valid items are retained. Invalid document-level
  responses return a useful error. Model-generated confirmation flags are ignored.
- Extracted professor rubrics are editable drafts. Absent rubrics use the existing
  deterministic defaults. Final saving runs the unchanged `validate_question`
  field checks and SymPy solution validation; invalid questions never become
  markable. The existing mathematics support limits still apply.
- Draft revisions and question fingerprints reject stale confirmations.
  Existing submissions for the same assignment/student cause a conflict,
  including partial imports and missing-ID namesakes. There is no automatic
  replacement of reviewed/published work; resume existing submissions instead.
- Drafts and rendered pages live under ignored `data/tutorial_imports/`.
  Original PDF bytes are not retained; hashes, filenames and every rendered page
  are retained. Source-page references and raw extraction/identity audit records
  accompany normal Question/Submission objects. Runtime records are not fixtures
  and must not be committed.
- Commits use the existing process lock, atomic file replacement and rollback of
  new/existing files together. The JSON store still requires a single backend
  process. A process crash is not a database transaction; an interrupted import
  may require manual recovery, but cannot publish student results.

## Endpoints

All are instructor workflow endpoints under `/api`:

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/assignments/{id}/imports/questions` | Multipart question PDF to editable draft. |
| POST | `/tutorial-imports/{id}/confirm-questions` | Confirm ordered prompts; requires draft revision. |
| POST | `/tutorial-imports/{id}/solutions` | Multipart solution PDF and revision to draft mappings. |
| POST | `/tutorial-imports/{id}/confirm-solutions` | Confirm mappings/rubrics and validate/save final questions. |
| POST | `/assignments/{id}/imports/student` | Multipart student PDF to editable answer draft. |
| POST | `/tutorial-imports/{id}/confirm-answers` | Confirm identity/mappings and create private submissions. |
| POST | `/tutorial-imports/{id}/mark` | Mark incomplete submissions through the existing pipeline. |
| GET | `/assignments/{id}/imports` | List persisted imports for resuming. |
| GET | `/tutorial-imports/{id}` | Read one saved import. |
| GET | `/tutorial-imports/{id}/pages/{page}?solution=false` | Inspect a retained original page; `solution=true` selects solution pages. |

Confirmation requests carry the displayed revision and edited structured rows;
solution/student rows require `confirmed: true`. The student confirmation request
also carries the confirmed identity. Every required question needs exactly one
mapped block, including unanswered questions. A missing answer uses `steps: []`;
no invented working is created. The existing marker receives that empty evidence
and the professor must inspect the resulting draft score/feedback.

## Calls, errors and limits

- Tutorial setup introduces two vision calls: one for the questions and one for
  the solutions. Each student PDF introduces one segmentation/transcription call.
  All pages are sent in one call, not one call per page.
- After explicit confirmation, each question uses the existing mark and feedback
  calls. There is no second transcription call per split answer and no automatic
  publication. Default rubric construction and SymPy validation make no API calls.
- Document responses reuse the existing content-addressed cache; ordered pages
  and the output schema contribute to document keys. Existing single-image cache
  keys and prompts are unchanged. Offline mode requires previously cached inputs.
  No new usage dashboard is added; the existing wrapper returns no usage metadata.
- **20 MB / 20 pages** per PDF, with an additional 18 MB rendered-image budget.
  Encrypted, empty, malformed or oversized documents are rejected before Claude.
  Truncated structured responses return an error; use a smaller source document.
- Marking reports per-question failures while retaining successful work. Retry
  only incomplete marking or open the failed question in Workbench. Completed
  marks/reviews are not regenerated by the import retry operation.
- Extraction is probabilistic: faint handwriting, uncertain labels, shared stems
  and complicated layouts require professor correction. Draft edits are saved
  at confirmation; navigating away before confirming loses local edits.
- This retains the prototype's existing unauthenticated instructor API model.
  It does not add authentication, analytics, chatbot controls or exam-specific
  ingestion. Live Claude output still needs a manual acceptance run; automated
  tests mock Claude and incur no API charges.

## Checks

From the repository root, run the backend with `DEMO_MODE=offline` for tests:

```powershell
$env:DEMO_MODE = "offline"
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest tests/test_tutorial_ingestion.py tests/test_llm.py -q -p no:cacheprovider
cd frontend
npm test
npm run build
```

The integration test renders the real synthetic fixture PDFs, mocks the three
document responses and per-question marking calls, and then exercises ordinary
review, progress, overrides, edited feedback and final group publication.
