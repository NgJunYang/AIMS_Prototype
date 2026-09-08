# Medium-priority fixes — verification

Implemented findings 5–8 from the original instructor-workflow QA. The frontend-design skill guided consistent use of the existing paper palette, typography and panels; no redesign was introduced.

| Finding | Delivered | Verified |
|---|---|---|
| No UI entry to released results | Open/copy result links from the workbench and Analytics details; Student result-code form | Browser: published Q2 result opened with edited feedback and 4/8 score. Unpublish + reload showed an unavailable message. Result-code access worked after republishing. Leaving the result for instructor mode cleared the result URL parameter. |
| Cannot resume after reload | Searchable saved-submission list in Setup and Resume marking in Analytics details | Browser: reload, locate QA script, resume restored Q2, working, manual C2=2, edited feedback and publication. Both resume entry points worked. API tests cover unmarked and marked records and safe saved-scan retrieval. |
| Phone layout overflow | Wrapping navigation/rubric headers, shrinkable cards and analytics grids, contained table scrolling, scrollable dialogs | Browser: 390x844 Setup, workbench, Analytics and Assignments had no document overflow. Desktop 1440x900 workbench retained all three panels. |
| CSV headers/order imported as students | Header mapping, strict row validation and all-or-nothing roster replacement; visible format instructions | Browser: student_id,name imported QA Alex/QA-M01 and QA Bea/QA-M02 (2 students). Unsupported header replacement was rejected while both original rows remained. |

## Checks

- Full Python suite: **1,044 passed, 32 skipped**.
- Frontend TypeScript and production build: passed; built assets updated.
- Lint: no errors; four existing warnings concerning Fast Refresh exports and callback dependencies remain.
- `git diff --check`: passed.
- Offline demo mode at `http://127.0.0.1:8001`; synthetic sample and roster data only. No live AI calls were enabled. Saved-image retrieval was automated-test coverage, not a fresh live OCR browser test.

## Limits

Resume restores saved data, not unsaved browser drafts or the original multi-page PDF. Student result links reuse the existing release gate, not a new identity/authentication system. The prototype still requires trusted access and synthetic data. Minor observations from the earlier report, including the stale updating message after an offline cache miss, are outside these four fixes.

## Cleanup

The QA submission `f606f73feb95`, assignment `qa-medium-0909`, and suite-generated `test-round-trip` record were moved recoverably into `tmp/qa-medium/archived/`. All pre-existing user records were left untouched. Browser testing overrides were reset and the test server stopped.
