# High-priority fixes — verification

Implemented the four high-priority findings from `instructor-workflow-2026-09-08.md`. Medium-priority findings remain deferred.

## Changes and browser regression results

| Original issue | Fix | Browser result |
|---|---|---|
| Setup changes the current script's question | Workbench references the submission's question ID; Setup preserves its selection | Q2 sample -> Setup remains Q2; deliberately choosing Q1 -> Workbench still shows Q2's prompt, model solution, and rubric editor |
| Refresh erases manual marks | Persist overrides independently of generated marks; unchanged working avoids invalidation | C2 changed from 1 to 2, total 4/8; unchanged refresh retained C2=2 and manual-edit indicator; explicit Reset restored 3/8 |
| Publish loses pending feedback | Keep a separate review draft; publication saves it with the release flag | Unsaved custom feedback survived a score edit and refresh, then appeared in the published student-view response |
| Publish loses corrected identity | Save name/ID with publication; add independent Save identity with saved/unsaved status | Corrected name appeared in Analytics; name and ID persisted on disk. Independent identity save also preserved pending feedback |

Additional checks: blank-name publication was blocked with a clear message, retaining pending feedback. Feedback survived Setup/Workbench navigation and explicit saving; saved feedback survived unchanged refresh. No browser console errors were captured.

The added identity control follows the existing warm-paper styling and panel layout; no redesign was introduced.

## Automated verification

- Full Python suite: **1,028 passed, 32 skipped**.
- Frontend TypeScript/production build: passed; generated static bundle updated. Existing large-bundle warning remains.
- Frontend lint: completed with four warnings (Fast Refresh exports and existing callback dependencies), no errors.
- `git diff --check`: passed.
- Added regression coverage for changed/unchanged transcription preserving overrides, legacy overrides surviving a failed remark/retry, explicit reset, rubric changes clearing incompatible overrides even while a remark is pending, reviewed feedback preservation, combined publication persistence, and rejected publication not partially saving data.

## Scope and limits

Browser verification used synthetic Q2 sample data, the rebuilt app at `http://127.0.0.1:8000`, and offline demo mode. Desktop 1440x900 displayed the existing three panels. At 390x844, the new identity save control fitted and worked; existing overall page overflow remained 533px and is still a deferred medium-priority issue. Live OCR/AI calls and arbitrary changed-transcription marking were not browser-tested; those persistence paths were covered by stubbed automated tests.

## Cleanup

QA records `47e1674594c4`, `4f26e9822e96`, `82eef7e34fd6`, and the full-suite fixture `test-round-trip` were moved recoverably to `tmp/qa-high-priority/archived/`. The two pre-existing submissions were left untouched. The test server was stopped, the browser tab closed, and viewport override reset.
