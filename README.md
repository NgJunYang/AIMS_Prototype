# SAINT — AI Marking Support

A tool that helps a lecturer mark handwritten algebra scripts (quadratics, at
present): a photo goes in, a lecturer-confirmed transcription, a symbolically
verified mark proposal, grounded feedback, and targeted practice questions
come out — with the lecturer able to override anything before it's final.

## The core idea

**SymPy is the only component in this system permitted to assert mathematical
truth.** The marking and feedback language models never re-derive or
re-check a single line of algebra; they receive the verifier's findings as
established fact and are explicitly instructed not to second-guess them
(`app/marker.py`'s prompt: *"Do NOT re-derive or re-check any mathematics...
If the findings say a step is equivalent, it is equivalent."*).

Why draw the line there: an LLM asked to check algebra will, fluently and
confidently, sometimes get the algebra wrong. A wrong mark stated with total
confidence is a much more dangerous failure than a wrong mark stated
tentatively — a lecturer double-checks a hedge, but has less reason to
double-check a confident, well-written justification. Routing every
mathematical judgement through a deterministic, exhaustively-testable module
(no LLM calls, no network access, no file I/O — see the docstring at the top
of `app/verifier.py`) means the one part of the system that decides "is this
step correct" can be tested exactly like any other pure function, and the
part that *can* hallucinate is kept strictly downstream of it, constrained to
judgement calls (how many rubric marks, how to phrase feedback) rather than
mathematical fact.

## The solution-set model

Every written line is an equation, so every line denotes a **solution set** —
the set of values of the unknown that satisfy it. A legitimate algebraic step
preserves that set. Comparing the solution set of line *n* to line *n − 1*
classifies what happened between them:

- **shrank** → a root was discarded (dividing both sides by the unknown,
  dropping a `±`)
- **grew** → a spurious root appeared (e.g. squaring both sides introduces one)
- **changed**, neither subset nor superset → an algebra or sign error

This is `app/verifier.py`'s `classify()`: divergence shapes map onto named
misconceptions (`divided_by_variable_lost_root`, `dropped_plus_minus`,
`sign_error`, `squaring_introduced_spurious_root`, ...) essentially for free,
because the comparison already encodes *what kind* of thing went wrong, not
just *that* something went wrong.

Two kinds of line are deliberately **not** solution sets to compare against
their neighbours, and treating them as such invents errors the student didn't
make:

- a line that can't be parsed as mathematics (`solution_set` returns `None`)
- an identity, true for every value of the unknown, e.g. a student checking
  their own factorisation (`solution_set` returns the sentinel `TAUTOLOGY`)

Both are skipped over rather than compared, so the comparison always runs
between lines either side of them. This module has already had six soundness
bugs fixed in it, every one of which turned an uninterpretable line into a
specific, plausible, *wrong* solution set that then fabricated a
misconception against a student who made no error — see the `test_bug1`
through `test_bug5` tests in `tests/test_verifier.py` for the exact shapes,
and `tests/test_adversarial.py` for the broader class of input this is
guarded against.

## Architecture / pipeline

| Stage | Module | What it does |
|---|---|---|
| Transcribe | `app/transcriber.py` | Vision LLM reads a photo into ordered LaTeX steps. Deliberately ignorant of the question, rubric, and model solution — its only job is to report what's on the page, mistakes included. |
| Confirm (human) | `app/main.py` (`PUT /steps`) | The lecturer edits/confirms the transcription. Nothing downstream runs on raw machine output. |
| Parse | `app/latex_utils.py` | Defensively turns one written line of LaTeX into SymPy equations, or fails closed to "unparseable" rather than guessing. |
| Verify | `app/verifier.py` | The only component allowed to assert mathematical truth — computes each line's solution set and classifies divergences. |
| Mark | `app/marker.py` | LLM proposes rubric marks, constrained to the verifier's findings; `cross_check()` flags any mark that contradicts them for the lecturer to review. |
| Feedback | `app/feedback.py` | LLM writes student-facing feedback grounded strictly in the marks and verification already decided — no new mathematical claims. |
| Practice | `app/practice.py` | Generates follow-up practice questions targeting the detected misconception. No LLM at all: each template declares its own answer, and a 150-case property test (`tests/test_practice.py`) checks the claimed answer actually solves the generated equation. |
| Retrieval | `app/context.py` | Deterministic keyed lookup (question, rubric, misconception explanations, course notes) for the LLM prompts — no vector store; the whole retrievable corpus is under two thousand tokens, so exact lookup is simpler and strictly more accurate than approximate search. |
| LLM gateway | `app/llm.py` | The only module that talks to the Anthropic API. Every call is content-addressed and cached to disk (`fixtures/llm_cache/`); in `DEMO_MODE=offline` a cache miss raises immediately instead of hanging on bad venue Wi-Fi. |
| Storage | `app/store.py` | The only file-I/O module: loads seed data, persists submissions. |
| API | `app/main.py` | FastAPI routes wiring the above together; serves the static frontend from `/`. |

## The human-in-the-loop boundary

Transcription is a machine guess and is treated as one: it is shown to the
lecturer, who confirms or edits it before anything else runs. Editing the
confirmed steps **invalidates everything computed from them** —
verification, marks, feedback and practice are all cleared
(`_invalidate_downstream` in `app/main.py`) — because a mark attached to
working the lecturer has since changed would be worse than no mark at all.
The system's guarantees only ever apply to what the lecturer has confirmed,
never to the raw transcription.

## Setup

```
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env          # Windows; cp on macOS/Linux
```

Then edit `.env` and set `ANTHROPIC_API_KEY` to a real key. `DEMO_MODE`
defaults to `live` in `.env.example` — see below for running with no key at
all.

## Run

```
.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

Use `python -m uvicorn`, not the bare `uvicorn` command — on Windows the
`uvicorn.exe` console-script shim installed into a venv can fail to resolve
correctly (PATH / shebang issues), while invoking it as a module through the
venv's own Python always works.

## Frontend

The frontend source lives in `frontend/` (React + Vite + Tailwind + Framer
Motion) and builds directly into `static/`, which the backend serves and
which GitHub Pages deploys — `static/` is generated output now, not
hand-edited.

```
cd frontend
npm install
```

Two ways to run it locally:

1. **Fast iteration** — Vite's dev server proxies `/api` to a separately
   running backend:
   ```
   npm run dev                                          # in frontend/, port 5173
   .venv/Scripts/python.exe -m uvicorn app.main:app --reload   # in another terminal, from repo root
   ```
2. **Production-path check** — build into `static/` and let uvicorn serve it
   exactly as it will in production:
   ```
   npm run build                                         # in frontend/
   .venv/Scripts/python.exe -m uvicorn app.main:app --reload   # from repo root, serves the build at http://localhost:8000
   ```

## Run the demo with no API key at all

This works today and is the fallback worth leading with if the venue Wi-Fi or
an API key is unavailable:

```
.venv/Scripts/python.exe scripts/seed_demo_cache.py
```

This hand-authors and writes plausible marking/feedback responses for the
flagship "divided through by x" script straight into `fixtures/llm_cache/`,
keyed exactly as a real API call would be. Then:

1. Start the server with `DEMO_MODE=offline` set (either in `.env`, or
   `set DEMO_MODE=offline` before the uvicorn command on Windows).
2. In the browser, choose question **q2**.
3. Click **"Use a sample script"** (not an upload — it pre-fills the confirm
   screen with the two lines `x^2 = 5x` then `x = 5`, so no transcription
   call is needed either).
4. Click **"Confirm & Mark"**.

The full verify → mark → feedback → practice pipeline runs end to end with
no network call and no API key, served entirely from the cache this script
just seeded.

## Resume marking and open released results

- **Setup → Resume saved marking** lists marked and unmarked submissions. Search by name, student ID, question or assignment, then choose **Resume marking**. Analytics student details also include a resume button.
- Resuming loads the last saved identity, confirmed working, marks, feedback and publication status. It does not recover unsaved browser edits. For a PDF, only the rendered page used for transcription is retained, not the original multi-page file.
- After publishing, use **Open student result** or **Copy result link**. The Student screen also accepts the result code. Reloading that link rechecks publication; unpublished test results are unavailable.
- Roster CSV headers can be `name,student_id` or `student_id,name`; `Student Name` and `Student ID` are accepted too. Headerless files must be name-first. Invalid rows, ambiguous recognised headers, and duplicate IDs reject the entire upload without replacing the existing roster.

This remains a trusted-demo prototype, not an authenticated student portal. Instructor APIs are not role-protected. Use synthetic data until authentication and authorisation are implemented. A localhost result link works only on the computer running the server.

## Tests

```
.venv/Scripts/python.exe -m pytest -q
```

992 tests currently pass. Notable groups:

- **`tests/test_seed_integrity.py`** — every model solution line in
  `app/seeds/questions.json` actually parses, and verifies as correct against
  itself. If the seed data itself were wrong, everything built on it would be
  wrong too; this catches that at the source.
- **`tests/test_practice.py`** — a 150-case property test (3 templates × 50
  seeds) asserting the claimed answer to every generated practice question
  actually solves the generated equation, since no LLM is involved in
  practice generation and nothing else checks it.
- **`tests/test_adversarial.py`** — robustness tests proving the pipeline
  degrades (returns `None` / flags "unparseable" / responds 4xx) rather than
  fabricates a misconception or a mark, when fed garbage strings, prose,
  non-equality relations, out-of-order or duplicate step indices, very long
  input, malformed LLM responses, malformed HTTP request bodies, and
  path-traversal attempts in a submission id.

## Known limitations

Stated plainly, because a demo that hides its limitations is easier for a
judge to distrust than one that names them:

- **Only quadratics in one variable are in scope.** The seed question bank,
  rubrics, misconception library, and practice generator are all built and
  tested against single-variable quadratics only. `app/verifier.py` itself
  does not hard-enforce that boundary — a cubic parses and solves correctly
  (see `tests/test_adversarial.py`) — but nothing else in the pipeline has
  been designed or exercised beyond it.
- **Complex roots display in SymPy/Python style**, e.g. `-1 + 2*I`, not as
  proper LaTeX (`-1 + 2i`), in the solution sets shown to the marking prompt
  and in places the frontend renders them raw.
- **Inequalities are rejected outright as unparseable**, not evaluated as
  inequalities. A line like `x \geq 2` degrades to "could not be interpreted
  as mathematics" rather than being verified on its own terms.
- **Transcription quality is the dominant, and currently unmeasured, source
  of error.** `scripts/evaluate.py` and `fixtures/ground_truth.json` exist to
  measure it honestly, but no real handwritten scripts have been photographed
  yet — every ground-truth entry is a placeholder, and running the evaluator
  today correctly reports "nothing could be evaluated" rather than a number.
  Do not take any transcription-accuracy figure on faith until that script
  has been run against real photographs.
- **The class-summary screen (`GET /api/class/summary`) is seeded fixture
  data** (`app/seeds/class_summary.json`), not computed from real
  submissions. It illustrates what the aggregate view would look like; it is
  not wired up to `data/submissions/`.
- A very long single line of alphabetic garbage (thousands of characters)
  is still correctly rejected as unparseable, but slowly — SymPy's LaTeX
  parser's error recovery is not linear in input length on pathological
  input. Not a correctness issue, but worth knowing before pasting an
  enormous line into the transcription editor.

## Deploying for judges (GitHub Pages + Render)

GitHub Pages can only serve static files; it cannot run FastAPI, SymPy, or an
LLM call with a hidden key. The included deployment therefore publishes only
`static/` to Pages and runs `app/` separately on Render.

### 1. Deploy the backend on Render

`render.yaml` defines the backend as a Render Blueprint:

1. Push or merge these changes to the repository's default branch.
2. On [render.com](https://render.com), choose **New → Blueprint**, connect
   this repository, and deploy it. Render reads `render.yaml` automatically.
3. Copy the exact HTTPS service URL shown by Render, for example
   `https://aims-backend-xxxx.onrender.com`. Render service URLs are unique, so
   do not assume the example URL is yours.

The Blueprint defaults to `DEMO_MODE=offline`, so cached demo flows work
without an API key. For live transcription and marking, set
`ANTHROPIC_API_KEY` and `DEMO_MODE=live` in the Render dashboard. Never put the
key in `static/`, a GitHub Actions variable, `render.yaml`, or a committed
`.env` file.

### 2. Configure the public backend URL

Do not edit `static/config.js`. Set the deployed backend URL once in GitHub:

1. Open **Settings → Secrets and variables → Actions → Variables**.
2. Create a repository variable named `AIMS_API_BASE` whose value is the exact
   Render service origin, for example `https://aims-backend-xxxx.onrender.com`.
   This URL is public browser configuration, not a secret; never put an API
   key in it.
3. Re-run **Deploy static frontend to GitHub Pages** under **Actions**, or push
   a frontend change to `main`.

During deployment, `.github/workflows/deploy-pages.yml` builds `frontend/`
into `static/`, copies `static/` to an isolated Pages artifact, and uses
`scripts/build_pages_config.js` to generate that artifact's `config.js` with
the configured URL. `frontend/public/config.js` (copied verbatim into every
build) stays empty so local development continues to use the same FastAPI
origin.

### 3. Enable GitHub Pages

Open **Settings → Pages** and, under **Build and deployment**, set **Source**
to **GitHub Actions**. Do not select a branch folder: `/static` is not a valid
branch-based Pages source. The workflow deploys on relevant pushes to `branch3`
or `improv2.0` and can also be started manually from the Actions tab.

After the workflow succeeds, the frontend is available at
`https://<owner>.github.io/<repository>/`. Its local CSS and JavaScript paths
are relative, so they work under the repository subpath. API and solution
image requests are resolved against `window.AIMS_API_BASE` and therefore go
to Render instead of GitHub Pages.

The backend currently allows cross-origin requests through
`ALLOWED_ORIGINS=*`, as configured in `render.yaml`. If you restrict it later,
use the Pages **origin** only (for example `https://t-zinlin.github.io`, with no
repository path) and include any custom-domain origin you use.

### 4. Deployment checks

1. Open `<your-render-origin>/api/health` and confirm it returns
   `{"status":"ok"}` before opening the Pages site. A free instance may take a
   short time to wake on its first request.
2. Confirm the Pages workflow completed successfully and open the URL shown in
   its `github-pages` deployment environment.
3. In the site, verify that the question list loads. If it does not, check the
   browser network panel: requests beginning with `/api/` must target the
   Render host, not `<owner>.github.io`.
4. Remember that offline mode supports cached demo inputs only. Enable live
   mode on Render to transcribe and mark previously unseen uploads.

This split changes only where the frontend and API are hosted. FastAPI still
serves `static/` directly during local development, and the marking pipeline
is otherwise unchanged.

## Not built yet

- Real handwritten fixtures. `fixtures/images/` is currently empty and
  `fixtures/ground_truth.json` contains only placeholder entries.
- A live evaluation run. `scripts/evaluate.py` is implemented and its
  "skip missing images, still print a summary" path is verified, but it has
  never been run against a real photograph, so no actual transcription
  accuracy, misconception precision/recall, or mark-agreement number has
  been measured yet.
