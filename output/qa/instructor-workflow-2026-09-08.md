# SAINT instructor workflow browser QA

Tested 7-8 September 2026 against local commit `c6b3d3c`, using the existing production assets served by FastAPI at http://localhost:8000. Application source and built assets were not changed. The browser was operated through the available computer/browser controls.

Environment: Windows, in-app browser, `DEMO_MODE=offline`. Viewports: 1440 x 900 desktop, 900 x 900 tablet, and 390 x 844 phone. Test data consisted of the built-in Q2 sample, synthetic names and IDs, a two-page synthetic PDF, a repository handwriting image, and two synthetic roster CSVs.

## Assessment

The basic sample marking demonstration works, but instructor edits can be lost and question context can become inconsistent. Fix issues 1-4 before relying on the app for the pitch. Publishing and resuming previous work also need connected UI flows.

## Confirmed findings

### 1. High: visiting Setup changes the active workbench to the wrong question

Reproduce:

1. From Setup, click **Use a sample script**. It creates Q2 with `x^2 = 5x` and `x = 5` and suggests 3/8.
2. Visit **Setup**, then click **Workbench** without creating another submission.
3. Expand **Question & model solution**, then open **Edit rubric**.

Actual: the workbench header and model solution now show Q1 (`x^2 - 5x + 6 = 0`, roots 2 and 3), while the response and marks remain Q2. The rubric editor explicitly says edits will re-score Q1. This was also observed after switching Student -> Instructor -> Workbench. With an assignment containing only Q2, returning to Setup can display Q1's prompt while the question select displays its placeholder.

Expected: an existing submission's workbench remains tied to that submission's question. Selecting the next question must not change the question or rubric being reviewed for the current script.

Source evidence: `frontend/src/pages/Setup.tsx:35` selects the first question on mount. `frontend/src/pages/Confirm.tsx:85`, `:185`, and `:243` use that shared current question for the header, reference and rubric editor.

### 2. High: refreshing unchanged working erases manual score overrides

Reproduce:

1. Create the Q2 sample.
2. Change C2 from 1 to 2 and move focus out of the field. Confirm the total changes to **4/8, manually adjusted total**.
3. Click **Refresh suggestions now** without changing any working.

Actual: C2 returns to 1, the total returns to **3/8**, and the manual-edit indicator disappears. No reset confirmation is shown, despite a separate **Reset rubric edits to AI suggestions** control existing.

Expected: preserve the instructor override unless explicitly reset, or clearly ask before discarding it.

Source evidence: `frontend/src/state/WorkbenchContext.tsx:353` updates steps before marking; the update invalidates downstream marks. `app/main.py:554` can only preserve overrides still present when marking starts.

### 3. High: Publish discards unsaved feedback

Reproduce:

1. Create a Q2 sample and edit **How to improve** to a distinctive value, such as `QA unsaved feedback to publish`.
2. Leave **Save feedback edits** unclicked.
3. Click **Publish to student**.

Actual: publishing succeeds; the edited text disappears and the original generated feedback replaces it. The unsaved indicator disappears too.

Expected: save pending feedback as part of publishing, or block publishing and prompt the instructor to save. Pending text must not be silently discarded.

Source evidence: `frontend/src/pages/Confirm.tsx:450` resets the draft when the feedback prop changes; publishing replaces the submission response. The Publish control is not disabled for pending feedback edits.

### 4. High: corrected student name/ID is not saved when publishing

Reproduce:

1. Create a sample named `QA Identity Check`.
2. In Source scan, change the name to `QA Corrected Identity` and the student ID to `QA003`.
3. Click **Publish to student**, then open **Analytics**.

Actual: the workbench displays the corrected name/ID, but analytics and the saved submission retain `QA Identity Check` and an empty student ID. Publishing succeeds without warning about the unsaved identity.

Expected: save identity corrections independently or as part of publishing, with an explicit saved/unsaved state.

Source evidence: identity persistence is inside `confirmAndMark` at `frontend/src/state/WorkbenchContext.tsx:355`. Editing identity alone does not trigger the transcription auto-refresh.

### 5. Medium: no student UI route to instructor-published results

Reproduce:

1. Publish a graded sample from the workbench.
2. Switch to **Student**.
3. Look for the released result, an assignment result list, or a way to open the submission.

Actual: the Student screen only offers a new tutorial upload/manual entry. Publishing produces no results link. The existing result cannot be opened through this screen.

Expected: a published result link or a student results list that opens the released submission.

Backend distinction: the student-view endpoint correctly returned the saved 4/8 score and edited feedback for the published QA sample. Unpublishing another sample made its student-view endpoint return 403. This is a missing UI connection, not a failure of the basic backend publication flag.

Source evidence: `frontend/src/pages/Student.tsx:64` stores a newly created submission ID locally; `:137` loads results after scoring that new tutorial submission.

### 6. Medium: a browser reload prevents resuming the marking session

Reproduce:

1. Create and mark a sample.
2. Reload the browser page.
3. Enter instructor mode again.

Actual: Workbench is disabled. Saved entries remain in Analytics, but its detail modal provides no reopen/edit action. Setup offers creation of another submission, not resumption of the existing one.

Expected: restore the active submission or provide a submission list with a Resume marking action. Persisted data was not erased; access to continue editing it was lost.

Source evidence: screen and workbench state initialize in memory at `frontend/src/App.tsx:32` and `frontend/src/state/WorkbenchContext.tsx:84`.

### 7. Medium: phone layouts overflow and clip important controls

Reproduce:

1. Open the workbench at 390 x 844.
2. Inspect the top navigation and rubric header; also visit Analytics.

Actual: the workbench document is 533px wide in a 390px viewport. Analytics and Student navigation extend off-screen. The rubric header clips the review badge. The analytics document measured 564px wide and its concept bars/text extend beyond the viewport.

Expected: navigation and content fit or use deliberate, clearly contained scrolling. Desktop displayed three usable panels. At 900px, the workbench stacked vertically and the tested analytics page did not overflow horizontally.

Source areas: navigation in `frontend/src/App.tsx`, rubric header in `frontend/src/pages/Confirm.tsx:224`, analytics grid in `frontend/src/pages/Class.tsx:126`.

### 8. Medium: roster CSV header/order errors silently become student data

Reproduce:

1. Create an assignment and upload a CSV with these rows:

```csv
student_id,name
QA001,QA Instructor Demo
QA002,QA Second Student
```

Actual: the app reports **3 students**, imports the header as a student, and treats IDs as names and names as IDs. No upload preview or format warning is shown.

Expected: map recognized headers, or reject unsupported column order with a clear format example. Do not silently turn column headings into roster records.

Control check: uploading the same two students with `name,student_id` headers correctly imports **2 students**. The current parser intentionally expects name first, but the UI does not state that requirement.

Source evidence: `app/assignments.py:30` parses by column position and only skips a header when its first cell resembles a name heading.

## Additional observations

- **Offline error leaves a misleading updating state:** change Q2's second line to `x = 0, x = 5`. Auto-refresh fires and reports an expected cache miss. The old marks remain alongside **Updating suggestions...** and **these will refresh in a moment**, even though the attempt has ended and no retry is scheduled. Restoring the cached lines and manually refreshing recovers. The cache miss is an environment limitation; the lasting progress message is an error-state UI problem.
- **Demo cohort note is inaccurate when live data exists:** choose **View demo cohort** after marking real sample submissions. The demo note says no submissions have been marked on this machine, even though live data exists. Label the selected view as illustrative without making that assertion.
- Student analytics rows open a detail modal, but the inspected modal had no visible close button. Escape successfully closed it.

## Passed checks and limits

| Check | Result |
|---|---|
| App startup using existing built assets | Passed |
| Q2 sample auto-marking and LaTeX rendering | Passed; 3/8, lost-root explanation and practice generated |
| Manual per-criterion score edit | Passed initially; 4/8 reflected in Analytics; refresh preservation fails as above |
| Out-of-range score | Passed; 99 rejected for a maximum-2 criterion with a clear error |
| Explicit feedback save | Passed; saved custom feedback survived navigation and appeared in analytics and student-view API |
| Publish/unpublish backend gating | Passed; published view readable, unpublished test view returns 403 |
| Practice show/hide and word-problem option | Passed; generated practice changed framing |
| Live analytics, concept breakdown and student detail | Passed for inspected sample records |
| Demo/live analytics switch | Passed, with misleading demo note noted above |
| Assignment creation and selection | Passed; Q2 assignment selected and a new submission stored its assignment ID |
| Roster import with supported name-first headers | Passed; two correct records |
| Two-page PDF inspection and navigation | Passed; both pages previewed, 1/2 and 2/2 controls updated |
| Handwritten image upload preview | Passed |
| Fresh OCR completion | Not verified; image and synthetic PDF produced explicit offline cache misses |
| Successful re-mark of novel corrected working | Not verified offline; cache miss reported and manual recovery exercised |
| Inline rubric editor | Open/cancel and wrong-question targeting inspected; rubric save/re-score not exercised against existing questions |
| New question authoring with OCR model solution | Not exercised in this offline run |
| Chatbot/email draft generation | Not exercised; outside the instructor-focused path and uncached AI behavior was not enabled |
| 1440px desktop | Three panels visible and usable |
| 900px tablet | Stacked workbench usable; tested analytics width fit |
| 390px phone | Failed horizontal overflow/clipping checks |

This was exploratory browser QA, not a new automated test suite. No claim is made that OCR accuracy, arbitrary mathematics, every assignment type, or live AI responses were validated.

## Test data and cleanup

QA-created records and uploaded images are archived under `tmp/qa-0907/archived/`, together with the synthetic test input files under `tmp/qa-0907/`. They were removed from the active data/image directories by recoverable moves, leaving the two pre-existing submissions untouched. The local test server was stopped after testing and the viewport override reset. No application code, production bundle or pre-existing question/rubric was changed.

Archived submission IDs:

- `91573a59d227`: QA Instructor Demo (saved feedback and 4/8 publication check)
- `095b775d133a`: QA Second Student (assignment and unsaved-feedback publication check)
- `15e1d1e0551a`: QA PDF Upload
- `f915a135a7d9`: QA Image Upload
- `37214d433a74`: QA Override Check
- `d3607b3ed96a`: QA Identity Check

Archived assignment: `qa-pitch-0907`.
