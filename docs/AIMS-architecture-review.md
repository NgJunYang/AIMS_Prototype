# AIMS — Architecture & Product Review

**AI for Individualised Mastery Support — hackathon prototype**
Review date: 2026-08-03
Status: pre-implementation analysis, awaiting clarifications

---

## 1. Understanding of the problem and proposed product

**Wider problem.** Lecturers with large cohorts cannot give timely, individual, formative feedback on open-ended work. Students receive a mark and a generic comment, which tells them their standing but not their misconception. The feedback loop that actually drives learning — *"here is the exact step where your reasoning broke, here is why, here are three problems that drill precisely that"* — does not scale with human marking.

**Narrowed prototype.** A lecturer-facing marking assistant for handwritten mathematics. The lecturer supplies a question, a model solution and a rubric; uploads a scan of a student's handwritten working; and the system transcribes it, checks the working step by step, proposes rubric-linked marks, writes student-facing feedback and generates targeted practice. The lecturer approves, edits or overrides everything before it is released.

**The critical framing.** This is **not** an autograder. It is a *decision-support tool that produces a reviewable draft*. That distinction should drive every design choice: the output must be traceable, editable and explainable, and the system must degrade gracefully rather than fail. An autograder that is 85% accurate is unusable; a draft-generator that is 85% accurate and shows its reasoning saves the lecturer most of the work.

---

## 2. Critical evaluation

### What is strong

- **The problem is real and well-chosen.** Marking maths working is genuinely laborious and genuinely under-served by existing tools (which mostly grade final answers only).
- **Step-level analysis is the right differentiator.** "Mark the method, not the answer" is what makes this pedagogically interesting and technically non-trivial.
- **Human-in-the-loop is correctly identified.** Most teams building this get seduced by full automation and produce something no lecturer would trust.
- **The misconception → practice loop is the genuinely novel part.** Auto-marking is a commodity. Closing the loop from "you made *this specific* error" to "here are problems that target *this specific* error" is not.

### What is weak or risky

**A. The pipeline is long and errors compound.** Eleven sequential steps, each with a failure probability, ending in a mark. If transcription is 90% accurate and step analysis is 90% accurate and rubric mapping is 90% accurate, end-to-end reliability is around 73%. Every extra stage you add multiplies the failure rate. The stage list needs pruning, not extending.

**B. OCR is the weakest link and it is stage one.** Handwritten mathematics recognition is a genuinely hard, unsolved problem — 2-D layout, ambiguous glyphs (`x`/`×`, `2`/`z`, `l`/`1`), inconsistent handwriting, poor phone photos. Traditional OCR (Tesseract) is effectively useless on maths. This is correctly flagged in the brief, but the mitigation is under-specified: an "edit the LaTeX" checkbox is not enough.

> **Recommended reframe:** the transcription-correction step is not a fallback. It is *the core interaction of the product.* The lecturer is already looking at the script; confirming a transcription takes five seconds and is far faster than marking. Design the UI around "confirm and correct", not around "hope the OCR worked". This converts your biggest technical risk into a designed feature, and it is honest — a judge who has tried maths OCR will respect it.

**C. RAG is almost certainly unnecessary here.** See §10 in full. Short version: your entire retrievable corpus (one question, one model solution, one rubric, a misconception catalogue, a few pages of notes) is a few thousand tokens. It fits in a single prompt. Adding chunking, embeddings, a vector store and retrieval tuning buys you nothing in accuracy and costs you a day of debugging plus a new class of silent failure (retrieving the wrong chunk). Build deterministic keyed retrieval instead. It is still retrieval-augmented, it is *more* accurate at this scale, and it is defensible to a judge.

**D. "Compares with relevant learning materials" is vague and low value.** What does the system do differently if it has the lecture notes? For marking: nothing. For feedback: it can cite "see Lecture 4, completing the square". That is a nice-to-have that costs almost nothing if you do keyed retrieval, and costs a day if you do vector RAG. Prioritise accordingly.

**E. Trusting an LLM to do the mathematics is the single biggest correctness risk.** LLMs make arithmetic and algebra errors, and — worse — they make them *confidently and fluently*. If the marking model is the same component that decides whether `x² − 5x + 6 = (x−2)(x−3)`, you will get plausible-sounding wrong marks. This is the failure mode most likely to embarrass you in front of judges.

> **Recommended fix:** invert the dependency. Run symbolic verification (SymPy) **first**, and feed its verdicts to the LLM as *given facts*. The LLM's job is then reduced to what it is actually reliable at: mapping verified facts onto rubric language and writing human feedback. It never decides mathematical truth. This is the strongest architectural idea in this document.

**F. Free-form LLM generation of practice questions is unsafe.** Ask a model for "five quadratics with integer roots that test sign errors" and some of them will not have integer roots. Handing a student a broken practice question destroys trust. Use parameterised templates with SymPy-verified answers instead — always correct, instant, and no API call.

**G. The single-student view under-sells the wider problem.** Your stated problem is *large classes*. A demo that marks one script does not visibly solve that. A class-level view — "31 scripts marked, 12 students lost a root by dividing through by x, here is the misconception ranked by frequency" — is cheap to compute over pre-marked fixtures and is what actually makes a lecturer lean forward. Strongly recommended as a headline demo moment.

**H. Missing: how does the lecturer author a rubric?** The brief assumes the rubric exists. Rubric authoring is real UX work. For the MVP: rubrics are JSON, pre-seeded for the demo, editable in a plain textarea. Do not build a rubric builder.

**I. Missing: multiple valid methods.** A student may complete the square while the model solution uses the formula. If your rubric criteria are phrased as "applied the quadratic formula correctly", every alternative method is marked wrong. Rubric criteria must be phrased method-agnostically where possible (e.g. "obtained a correct factorised or equivalent reduced form"), and the marking prompt must explicitly permit alternative valid methods. Have a deliberate demo case for this — it is an excellent moment.

**J. Not building anything.** The brief says avoid training a handwriting model. Correct, and go further: do not build image preprocessing (deskew, binarise, denoise) either. Modern vision models handle a phone photo better than a hand-rolled OpenCV pipeline, and preprocessing is a classic hackathon time sink with no visible payoff.

---

## 3. Strongest value proposition

> **Every student gets step-level, rubric-linked feedback and a personalised practice set in seconds — and the lecturer stays in control, because every proposed mark is traceable to a *verified mathematical fact*, not an AI guess.**

The three claims that make this defensible, in priority order:

1. **Verified, not guessed.** Symbolic checking underpins the marks. You can show the audit trail.
2. **Method, not answer.** The system finds *where* the reasoning broke, not just that the final number is wrong.
3. **Closes the loop.** Detected misconception → targeted, machine-verified practice. Feedback that produces action.

Everything else — the OCR, the UI, the RAG — is supporting machinery. Pitch these three.

---

## 4. A realistic, clearly bounded MVP

### In scope

One lecturer, one question, one student script at a time, plus a pre-computed class view.

| Stage | Description |
|---|---|
| **1. Setup** | Lecturer selects a question from a seeded library (question + model solution as an ordered step list + rubric as JSON, 3–5 criteria). Editable in a textarea. |
| **2. Upload** | Drag a photo/scan of handwritten working. Also: "use a sample script" and "type it in manually". |
| **3. Transcribe** | Vision model returns structured JSON: an ordered list of steps, each with LaTeX and a confidence flag. |
| **4. Confirm** | Side-by-side: original image left, editable LaTeX steps right (live-rendered). Low-confidence steps highlighted. Lecturer fixes and clicks Verify. **This is the core interaction.** |
| **5. Verify (symbolic)** | For each step: is it a valid consequence of the previous step? Does the final answer match the model's solution set? Where is the first divergence, and what kind is it? |
| **6. Mark** | LLM receives question + model + rubric + confirmed steps + the symbolic verification report + a misconception catalogue. Returns per-criterion marks with a justification and a pointer to the specific step that is the evidence. |
| **7. Feedback** | Student-facing prose: what was right, where and why it went wrong, how to fix it. Grounded strictly in stages 5–6. |
| **8. Practice** | 3 questions generated from parameterised templates keyed to the detected misconception, answers verified by SymPy. |
| **9. Review** | Lecturer edits any mark, any comment; total recomputes. Approve → export a feedback sheet (HTML/PDF). |
| **10. Class view** | Table of pre-marked scripts + a ranked bar chart of misconception frequency across the cohort. |

### Explicitly out of scope

No authentication. No LMS integration. No multi-tenant anything. No rubric builder UI. No batch upload of 30 real scans (the class view runs on fixtures). No mobile app. No student login. No handwriting model training. No image preprocessing pipeline. No vector database. No support for any topic outside the chosen one. No real student data of any kind.

### Definition of done

Given any of the six seeded demo scripts, the system produces marks, feedback and practice in under 30 seconds, and the whole flow can be run offline from cached fixtures if the network fails.

---

## 5. The mathematics topic to support first

**Recommendation: solving single-variable quadratic equations** — by factorising, completing the square, or the quadratic formula. Include the light algebraic rearrangement needed to get to standard form.

Why this beats the alternatives:

- **Linear step structure.** Each line is an equation. This makes the central symbolic check trivially expressible: *does line n have the same solution set as line n−1?* You get "mark the method" almost for free.
- **Simple handwriting.** Mostly one-dimensional. Digits, `x`, `+ − = ( )`, superscript `2`. The only awkward 2-D construct is the quadratic-formula fraction with a surd — and that is exactly one recognisable pattern.
- **A famous, well-documented misconception catalogue.** Sign error when factorising; dividing both sides by `x` and losing the root `x = 0`; dropping the `±`; sign error in the discriminant `b² − 4ac`; wrong constant when completing the square; misapplying the zero-product rule (`(x−2)(x−3) = 1 ⟹ x−2 = 1`); mishandling a negative discriminant. Seven crisp, recognisable, teachable errors — perfect for a demo and for a practice generator.
- **Trivially parameterisable practice.** Pick integer roots, expand, present. Guaranteed well-posed, SymPy-verifiable, instant.
- **Everyone in the room understands it**, including non-maths judges. The demo needs no explanation.

**Runner-up: single-variable differentiation** (product/quotient/chain rule). Also good — SymPy `diff` gives you an easy oracle and chain-rule errors are a rich misconception space. It loses because the notation is more two-dimensional (`dy/dx`, primes, nested fractions), which makes transcription harder, and because the "chain of equivalent lines" property is weaker, so step-level verification is less clean.

**Avoid entirely for the MVP:** integration (multiple valid forms, constants of integration, wildly varied notation), matrices and anything with 2-D layout, word problems, proofs, and anything involving diagrams.

If you finish early, differentiation is the natural second topic — the architecture should not need to change to add it, and *demonstrating* that extensibility (a second topic added in an hour) is itself a strong pitch point.

---

## 6. Essential vs optional features

### Essential — no demo without these

1. Question/model/rubric loaded from a seeded library
2. Image upload **and** a "use sample" path **and** manual entry
3. Image → structured LaTeX steps (vision model)
4. Editable, live-rendered LaTeX step list with an image side by side
5. SymPy step-to-step equivalence checking + final-answer check + first-divergence detection
6. LLM rubric marking grounded in the symbolic report, returning structured JSON with per-criterion justification and step evidence
7. Student-facing feedback text
8. Lecturer override on every mark and comment
9. Offline fixture mode (cached responses for the demo scripts)

### High value, do if on track

10. Misconception classification with named tags
11. Template-based, SymPy-verified practice generation
12. Class-level misconception dashboard (on fixtures)
13. Export/print a feedback sheet
14. Confidence highlighting on low-certainty transcription

### Optional — only with genuine spare time

15. Keyed retrieval of lecture-note snippets cited in feedback
16. A second topic (differentiation)
17. Per-step timing/telemetry panel showing the pipeline stages live (surprisingly good in a demo)
18. Semantic/embedding retrieval, if and only if you want to say "vector RAG" on a slide

### Do not build

Authentication, databases beyond SQLite, LMS integration, student-facing portal, real batch processing, mobile, image preprocessing, any model training or fine-tuning.

---

## 7. Recommended system architecture

### Principle: an explicit staged pipeline with persisted intermediate artefacts

Every stage reads a persisted artefact and writes a persisted artefact. Nothing is held only in memory or only in a single long LLM call.

```
                 ┌──────────────────────────────────────────────┐
                 │  React SPA (Vite + TS)                        │
                 │  Upload → Confirm LaTeX → Review marks →      │
                 │  Feedback → Practice → Class view             │
                 └───────────────────┬──────────────────────────┘
                                     │ REST/JSON
                 ┌───────────────────▼──────────────────────────┐
                 │  FastAPI (Python)                             │
                 │                                               │
                 │  /submissions            (create, upload)     │
                 │  /submissions/{id}/transcribe                 │
                 │  /submissions/{id}/steps  (PUT — corrections) │
                 │  /submissions/{id}/verify                     │
                 │  /submissions/{id}/mark                       │
                 │  /submissions/{id}/practice                   │
                 │  /submissions/{id}/override                   │
                 │  /class/summary                               │
                 └───┬──────────┬──────────┬─────────┬──────────┘
                     │          │          │         │
        ┌────────────▼──┐  ┌────▼──────┐ ┌─▼───────┐ ┌▼─────────────┐
        │ Transcriber   │  │ Verifier  │ │ Marker  │ │ Practice Gen │
        │ vision LLM    │  │ SymPy     │ │ LLM +   │ │ templates +  │
        │ → step JSON   │  │ pure fn   │ │ schema  │ │ SymPy check  │
        │ NO marking    │  │ NO LLM    │ │ NO math │ │ NO LLM       │
        └───────────────┘  └───────────┘ └────┬────┘ └──────────────┘
                                              │
                                     ┌────────▼─────────┐
                                     │ Context Assembler│
                                     │ keyed lookup:    │
                                     │ rubric, model    │
                                     │ soln, misconcep- │
                                     │ tion catalogue,  │
                                     │ note snippets    │
                                     └──────────────────┘

        Storage: SQLite (submissions, steps, verifications, marks)
                 + filesystem (images)
                 + JSON seed files (questions, rubrics, catalogue, templates)
```

### The four hard boundaries

These separations are the whole design. Enforce them in code review.

1. **The transcriber never marks.** It is given the image and asked only "what is written here?" It does not see the model solution. If it did, it would hallucinate the expected working into the transcription — a subtle, demo-destroying failure that is very hard to notice.
2. **The verifier never calls an LLM.** It is a pure, deterministic, unit-testable Python function: `verify(steps, model_solution) -> VerificationReport`. It is the only component permitted to assert mathematical truth.
3. **The marker never does mathematics.** It receives the verification report as ground truth and maps it onto rubric criteria and prose. If the marker's justification contradicts the verification report, that is a bug — and you can detect it automatically.
4. **The practice generator never invents questions.** It instantiates verified templates.

### Why staged persistence matters for a hackathon

- Each stage is independently demoable — if the marker is broken at 3 a.m., the transcribe-and-verify demo still works.
- Any stage can be re-run without redoing the expensive ones.
- Every stage can be replaced by a cached fixture, which is your offline fallback.
- Four people can work on four stages in parallel against a fixed JSON contract.

**Define the JSON contracts on day one, before anyone writes logic.** This is the single highest-leverage hour of the whole project.

### Core data shapes (sketch)

```jsonc
// Step (after transcription, before/after correction)
{ "index": 1, "latex": "x^2 - 5x + 6 = 0", "confidence": "high|low", "edited_by_human": false }

// VerificationReport
{
  "steps": [
    { "index": 1, "parsed": true, "equivalent_to_previous": null, "note": "initial" },
    { "index": 2, "parsed": true, "equivalent_to_previous": true },
    { "index": 3, "parsed": true, "equivalent_to_previous": false,
      "divergence": "solution_set_changed", "lost_roots": ["0"] }
  ],
  "final_answer_correct": false,
  "first_divergence_index": 3,
  "candidate_misconceptions": ["divided_by_variable_lost_root"]
}

// MarkProposal
{
  "criteria": [
    { "id": "C1", "description": "Rearranged to standard form", "max": 2,
      "proposed": 2, "justification": "...", "evidence_step": 1 },
    { "id": "C2", "description": "Correct method applied", "max": 3,
      "proposed": 1, "justification": "...", "evidence_step": 3 }
  ],
  "total_proposed": 3, "total_max": 8,
  "misconceptions": ["divided_by_variable_lost_root"]
}
```

---

## 8. Recommended technology stack

| Layer | Choice | Reasoning |
|---|---|---|
| Frontend | **React + Vite + TypeScript** | Fast HMR, everyone knows it, TS catches contract drift between stages. |
| Math rendering | **KaTeX** | Faster and lighter than MathJax; sufficient for this notation. |
| Math editing | **MathLive** (`<math-field>`) | Proper editable maths field. **Fallback: a plain textarea of LaTeX with a live KaTeX preview.** Ship the textarea first — it is 20 minutes' work and never breaks; upgrade to MathLive only if time allows. |
| Styling | **Tailwind** | Fast, and keeps the UI looking deliberate rather than default. |
| Backend | **Python + FastAPI** | SymPy is Python; the verification core is the heart of the system, so the backend must be Python. Pydantic gives you schema validation on LLM outputs for free. |
| Symbolic engine | **SymPy** | `sympy.parsing.latex.parse_latex` (needs `antlr4-python3-runtime`), `solveset`, `simplify`, `Eq`. |
| LLM | **Claude** (`claude-opus-5` for marking, `claude-sonnet-5` for transcription/speed) | Strong vision, strong structured output, one vendor for both stages. Use tool-use / JSON schema for structured outputs — never parse free text. Temperature 0 everywhere. |
| Storage | **SQLite** via SQLModel, images on disk | Zero setup, file-based, trivially resettable for the demo. |
| Seed data | **JSON files in the repo** | Questions, rubrics, misconception catalogue, practice templates, cached fixtures. Version-controlled, diffable, editable by non-coders. |
| Charts | **Recharts** | One bar chart for the class view. |
| Config | **`.env` + `python-dotenv`**, server-side only | See security note below. |
| Dev | `uv` or `venv` + `pip`, `npm`, `ruff`, `pytest` | Keep it boring. |

### What to deliberately *not* use

- **Tesseract / OpenCV preprocessing** — useless on maths, and a time sink.
- **A vector database (Chroma/FAISS/Pinecone)** — see §10.
- **LangChain / LlamaIndex** — the abstraction cost exceeds the benefit for four LLM calls; direct SDK calls are clearer and easier to debug at 2 a.m.
- **Postgres / Docker Compose / Kubernetes** — nothing here needs them.
- **Mathpix** — genuinely the best maths OCR, but it is a paid second vendor with its own key and quota. Use the multimodal LLM. *Consider Mathpix only if transcription quality turns out to be the demo blocker and you have budget.*

### Security (in scope, small effort, worth a slide)

- API keys in `.env`, loaded server-side only, `.env` in `.gitignore`, `.env.example` committed. **Never** put a key in the frontend bundle.
- All LLM calls proxied through your backend; the browser never talks to the model provider.
- No real student data. Fabricate all names. The demo scripts are written by team members. Add a one-line "images are processed in memory and not retained beyond the session" statement and actually honour it (or make retention explicit and deletable).
- Add a `DEMO_MODE=offline` flag that serves everything from fixtures with no network egress at all.

---

## 9. How OCR, LaTeX, RAG and mathematical verification interact

The order and the direction of dependency are what matter.

```
IMAGE
  │
  ▼
[TRANSCRIBE]  vision LLM, sees ONLY the image + a notation guide
  │           "Return an ordered JSON list of the written lines as LaTeX.
  │            Do not solve. Do not correct. Transcribe exactly, including errors.
  │            Flag any line you are unsure of."
  ▼
STEPS (LaTeX)  ── low-confidence lines flagged
  │
  ▼
[HUMAN CONFIRM]  ◄── THE TRUST BOUNDARY
  │              Everything upstream is a suggestion.
  │              Everything downstream operates on human-confirmed input.
  ▼
CONFIRMED STEPS
  │
  ▼
[VERIFY]  SymPy, deterministic, no LLM
  │       • parse each LaTeX line to a SymPy Eq (try/except every parse)
  │       • solution set of line n vs line n−1  → equivalent? roots lost/gained?
  │       • final answer vs model solution set  → correct?
  │       • locate first divergence, classify its shape
  ▼
VERIFICATION REPORT  ── ground truth, machine-checked
  │
  ├──────────────► [CONTEXT ASSEMBLER]  keyed lookup, no embeddings
  │                 • the rubric JSON
  │                 • the model solution step list
  │                 • misconception catalogue entries matching the divergence shape
  │                 • (optional) note snippets tagged with this topic
  ▼
[MARK]  LLM with a strict output schema
  │     Receives verification report as GIVEN FACTS.
  │     "You may not re-derive the mathematics. Use only the verified findings.
  │      For each rubric criterion, propose a mark, justify it, and cite the step."
  ▼
MARK PROPOSAL (per-criterion, with evidence step refs)
  │
  ├──► [FEEDBACK]  LLM, prose, grounded strictly in the above
  │
  └──► [PRACTICE]  templates keyed by misconception tag, answers SymPy-verified
                   (NO LLM in this path)
                          │
                          ▼
                   [LECTURER REVIEW & OVERRIDE] ──► EXPORT
```

**The two rules that make this work:**

1. **Verification precedes and constrains marking.** The LLM never adjudicates mathematical truth. This eliminates the most damaging failure mode.
2. **The human confirm step is a hard trust boundary.** Do not let the pipeline run end-to-end without it in the primary demo path. (Offer an "auto-run" button for speed, but make the confirm step the story.)

**Automatic consistency check (cheap, high value):** if the marker awards full credit on a criterion whose evidence step the verifier marked non-equivalent, flag it in the UI as *"AI marking disagrees with symbolic check — please review"*. This is a genuinely impressive safety feature, costs about fifteen lines of code, and demonstrates that you thought about AI reliability.

---

## 10. Is RAG genuinely useful here?

**Short answer: not as vector-search RAG. Yes as deterministic keyed retrieval.**

### The argument

Vector RAG exists to solve one problem: *the corpus does not fit in the context window, so find the relevant slice.* Your corpus is:

| Item | Approx. size |
|---|---|
| The question | 50 tokens |
| The model solution (step list) | 200 tokens |
| The rubric (3–5 criteria) | 300 tokens |
| Misconception catalogue (7 entries for quadratics) | 700 tokens |
| Relevant lecture-note snippets | 500 tokens |
| **Total** | **~1,800 tokens** |

You have a 200k context window. There is no retrieval problem to solve. Introducing embeddings would mean chunking, an embedding model, a vector store, a similarity threshold to tune, and a new silent failure mode where the *wrong* rubric chunk gets retrieved and the marking is quietly wrong. You would spend a day of your hackathon making the system less accurate.

### What to build instead

A `ContextAssembler` module with a deterministic interface:

```python
def assemble(question_id: str, misconception_tags: list[str]) -> Context:
    """Exact lookups against seed JSON. No similarity, no threshold, no surprises."""
```

Backed by JSON seed files keyed by `question_id`, `topic_tag` and `misconception_tag`. This *is* retrieval-augmented generation — the generation is augmented by retrieved documents. It is simply exact retrieval rather than approximate, which at this corpus size is strictly better. Say that plainly to judges; a good judge will agree, and it demonstrates engineering judgement rather than buzzword compliance.

### What should be retrieved

| Retrieved item | Keyed by | Used by | Genuinely needed? |
|---|---|---|---|
| Rubric criteria | question_id | Marker | **Yes — essential** |
| Model solution steps | question_id | Verifier, Marker | **Yes — essential** |
| Misconception catalogue entry (name, description, why students do it, remediation phrasing) | divergence shape / misconception_tag | Marker, Feedback | **Yes — high value.** This is what makes feedback pedagogically credible rather than generic. |
| Practice templates | misconception_tag | Practice generator | **Yes** |
| Lecture-note snippet ("see §4.2, completing the square") | topic_tag | Feedback | Nice-to-have. Adds credibility to feedback citations for very little cost. |
| Worked examples | topic_tag | Feedback | Marginal. Skip unless time is left over. |

### The optional upgrade

If, with genuine spare time, you want an embedding-based path on a slide: add a `SemanticContextAssembler` behind the *same interface*, over the note snippets only, with a toggle in the UI to compare the two. That is a one-to-two hour job at the end and demonstrates the architecture's extensibility. It is a presentation feature, not a correctness feature. Do not build it first.

---

## 11. Main technical risks and fallback strategies

Ordered by expected damage.

| # | Risk | Likelihood | Impact | Mitigation / fallback |
|---|---|---|---|---|
| 1 | **Transcription is unreliable on real handwriting** | High | High | Editable LaTeX is the primary UX, not a fallback. Plus: (a) six *golden* demo scripts written neatly in dark pen on plain white paper, photographed in good light, with cached transcriptions committed to the repo; (b) a "type it in" path; (c) a "load sample" path. **Never let the demo depend on a live transcription of an unseen image.** Invite the audience to try their own *after* the scripted demo succeeds. |
| 2 | **No/flaky venue Wi-Fi during the demo** | Medium | Fatal | `DEMO_MODE=offline` serving every LLM response from committed fixtures, keyed by a hash of the input. Build this on day two, not day five. Test it with the laptop in flight mode. |
| 3 | **LLM produces a mark contradicting the symbolic check** | Medium | High | Automatic cross-check (§9) surfaces the disagreement in the UI as a warning. Turns a bug into a feature. |
| 4 | **`parse_latex` fails on valid student LaTeX** | High | Medium | Wrap *every* parse in try/except. On failure: mark that step `parsed: false`, continue the pipeline, degrade to LLM-only marking for that step with a visible "not symbolically verified" badge. Never let a parse error 500 the request. Normalise common LaTeX variants (`\times`, `\cdot`, `\left(`, `\dfrac`) before parsing. |
| 5 | **Scope creep** | High | High | Freeze the topic and the feature list at the end of day two. Maintain an explicit "after the demo" list; anything new goes there by default. |
| 6 | **Integration hell on the last day** | High | High | Contracts (JSON schemas) defined hour one. Every stage has a fixture-backed stub from hour two, so the full pipeline runs end-to-end on fake data before any real logic exists. Integrate continuously, never at the end. |
| 7 | **Latency makes the demo drag** | Medium | Medium | Temperature 0, parallelise independent calls, stream feedback text, show per-stage progress indicators (which double as an architecture explainer). Pre-warm by running the demo script once before presenting. |
| 8 | **Alternative valid method marked wrong** | Medium | Medium | Method-agnostic rubric phrasing; explicit permission in the marking prompt; a deliberate demo case showing it handled correctly. |
| 9 | **API key leaked / committed** | Low | High | `.gitignore` from commit one, `.env.example`, server-side only. Add a pre-commit grep for `sk-` if you want belt and braces. |
| 10 | **Cost overrun** | Low | Low | Fixtures during development mean you barely call the API. Cache aggressively. Set a spend limit. |
| 11 | **A team member's environment breaks** | Medium | Medium | Pin versions, commit a lockfile, one documented setup command, verify on all machines on day one — not day four. |

---

## 12. Suggested user interface and demonstration flow

### UI: four screens

**Screen 1 — Assignment setup.** Question picker (dropdown of seeded questions). Model solution shown as a numbered step list. Rubric shown as a table of criteria with max marks. Everything editable in place. One "Upload student work" button.

**Screen 2 — Transcribe & Confirm** *(the signature screen)*.
Split pane. Left: the original scan, zoomable. Right: the numbered step list, each row a live-rendered LaTeX line that becomes editable on click. Low-confidence rows tinted amber with a small "check this" marker. Buttons: `Add step`, `Delete step`, `Reorder`. One primary action: **Confirm & Mark**.

**Screen 3 — Marking review** *(the payoff screen)*.
Three columns:
- *Left:* the confirmed steps, each annotated with a symbolic verdict — green tick (valid consequence), amber (unverifiable), red cross (not equivalent, with the reason: "solution set changed: root x = 0 lost").
- *Centre:* the rubric table. Per criterion: proposed mark (editable number input), justification text, and a clickable link to the evidence step which highlights it on the left. Running total at the bottom, updating live as the lecturer overrides.
- *Right:* tabs — **Feedback** (student-facing prose, editable) · **Misconceptions** (named tags with explanations) · **Practice** (three generated questions with worked answers).

Footer: `Approve & Export`.

**Screen 4 — Class view.** A table of all scripts (student pseudonym, mark, top misconception, status) and a horizontal bar chart of misconception frequency across the cohort. One line of interpretation underneath: *"12 of 31 students lost a root by dividing through by x — consider revisiting the zero-product principle."*

### Demo script (target: 5 minutes)

| Time | Beat |
|---|---|
| 0:00 | **Problem, in one sentence, with a number.** "This lecturer has 240 students. Marking one set of quadratics scripts properly takes eleven hours. So students get a number and a tick." |
| 0:30 | **Setup.** Show the question, model solution and rubric. Five seconds — do not dwell. |
| 0:45 | **Upload a real handwritten scan.** Let it transcribe live. |
| 1:15 | **Confirm.** The system flagged line 3 as uncertain; it read `5x` as `sx`. Fix it in two clicks. *Say the line:* "Handwriting recognition will never be perfect — so we designed for that. The lecturer confirms in seconds, and everything after this point is built on verified input." **This is your credibility moment. Do not hide it — lead with it.** |
| 1:45 | **Mark.** Show the symbolic verdicts appearing per step. Land on the red cross at step 3: *"Solution set changed — the root x = 0 was lost."* "That is not the AI's opinion. That is a computer-algebra system checking the algebra." |
| 2:30 | **Rubric marks.** Point at a justification and click through to its evidence step. Override one mark to show the lecturer is in control; watch the total update. |
| 3:00 | **Feedback and practice.** Read two lines of the student feedback aloud. Show the three practice questions. "These target the exact misconception, and every answer is machine-verified — the student can never be handed a broken question." |
| 3:30 | **The alternative-method case.** Load a second script that completes the square instead. Full marks. "It marks the mathematics, not the template." |
| 4:00 | **Class view.** The bar chart. "And across the cohort, here is what the lecturer should reteach on Monday." *This is the moment that connects back to the opening.* |
| 4:30 | **Close.** Architecture diagram, one slide. Three sentences: verified not guessed; method not answer; lecturer always in control. |

**Demo discipline:** rehearse it end to end at least three times. Use fixed, seeded inputs. Have the offline mode loaded and tested. Have a screen recording of a successful run on the desktop as the ultimate fallback.

---

## 13. Development plan for four to five people

Duration is unconfirmed (see questions). This plan is expressed in five phases; compress or expand each proportionally to your actual window.

### Phase 0 — Contracts and skeleton *(first ~10% of time; everyone, together, in one room)*

The most important phase. Do not skip it and do not let anyone start "real work" during it.

- Agree the topic and freeze it. Write the scope statement and the out-of-scope list on a wall.
- **Define every JSON contract**: `Question`, `Rubric`, `Step`, `VerificationReport`, `MarkProposal`, `Feedback`, `PracticeSet`. Commit them as Pydantic models and TypeScript types.
- Scaffold: FastAPI app with every endpoint returning a hard-coded fixture; React app that walks the full four-screen flow against those fixtures.
- **Exit criterion: the complete demo flow runs end to end on fake data.** From here on, every task replaces one fixture with real logic, and the demo never breaks.
- Repo, `.gitignore`, `.env.example`, one-command setup, verified on every laptop.

### Phase 1 — Vertical slice, one question *(next ~25%)*

- One question, one rubric, one handwritten script.
- Real transcription for that image; real SymPy verification; real LLM marking.
- The confirm screen works with a plain textarea + KaTeX preview.
- **Exit criterion: one real script goes image → marks, live.** Ugly is fine.

### Phase 2 — Breadth and robustness *(next ~30%)*

- Six demo scripts covering the misconception range.
- Misconception classification and the catalogue.
- Practice generation from templates.
- Feedback generation and the review/override UI.
- Offline fixture mode built and tested in flight mode.
- Every parse and every API call wrapped in error handling.
- **Exit criterion: all six scripts work; unplugging the network does not break the demo.**

### Phase 3 — Polish and the class view *(next ~25%)*

- Visual design pass (Tailwind, spacing, typography — this disproportionately affects judging).
- Class dashboard on fixtures.
- MathLive upgrade if the textarea feels clumsy.
- Export/print feedback sheet.
- The AI-vs-symbolic disagreement warning.
- Evaluation numbers computed and put on a slide (§16).
- **Feature freeze at the end of this phase.** Non-negotiable.

### Phase 4 — Demo hardening *(final ~10%)*

- No new features. Bug fixes and rehearsal only.
- Three full rehearsals, timed.
- Screen recording as backup. Slides finished. Q&A prep (see below).
- Everyone knows their speaking part and can answer for their component.

**Prepare answers to these judge questions:** *What if the OCR is wrong? How do you know the marks are right? Why not just use an LLM end to end? What stops a lecturer from rubber-stamping bad marks? How does this scale past quadratics? What about student privacy?*

---

## 14. Division of responsibilities

Designed so that each person owns one module behind a fixed interface, and nobody blocks anybody.

**With five people:**

| Role | Owns | Deliverables |
|---|---|---|
| **A — Frontend & UX** | React app, all four screens | Upload, confirm/edit LaTeX, marking review, class view, export, styling. The demo is largely this person's craft. |
| **B — Transcription** | `Transcriber` module | Prompt + output schema, notation guide, confidence flagging, LaTeX normalisation, cached fixtures for all demo images. |
| **C — Symbolic engine** | `Verifier` + `PracticeGenerator` | SymPy parsing, step-equivalence, divergence classification, misconception mapping, practice templates. Heaviest pure-Python work; give this to your strongest maths/algorithms person. |
| **D — Marking & feedback** | `Marker` + `FeedbackWriter` + `ContextAssembler` | Rubric schema, prompt design, structured outputs, grounding rules, misconception catalogue authoring, the disagreement cross-check. |
| **E — Integration, data & demo** | FastAPI glue, storage, offline mode, dataset, evaluation, presentation | Endpoints, SQLite, fixture system, the six handwritten scripts, ground-truth marking, evaluation harness, demo script, slides. Also the integrator-of-last-resort and the one who says no to scope creep. |

**With four people:** merge E into A (glue and demo) and C (data and evaluation). Keep B, C and D separate — those are the three genuinely parallel technical tracks.

**Working agreements worth stating explicitly:**
- Contracts change only by agreement of the whole team, announced in the group chat.
- Every module ships with a fixture so downstream work is never blocked.
- Commit and push at least every two hours. Short-lived branches, frequent merges to `main`.
- One person (E) owns `main` being demoable at all times.
- Twice-daily fifteen-minute standups: what works, what is blocked, what is at risk.

---

## 15. Sample data to prepare

Prepare this **early** — probably during Phase 0/1. Teams routinely leave data until last and then discover their pipeline has never seen realistic input.

### Questions and rubrics — six to eight

Written as JSON seed files. Suggested spread:

1. `x² − 5x + 6 = 0` — factorises cleanly (the "everything works" case)
2. `x² = 5x` — the divide-by-x trap (loses `x = 0`)
3. `2x² + 3x − 5 = 0` — requires the formula or careful factorising
4. `x² + 4x + 1 = 0` — irrational roots, needs the formula or completing the square
5. `x² + 2x + 5 = 0` — negative discriminant, no real roots
6. `(x − 2)(x − 3) = 2` — the zero-product misapplication trap
7. *(stretch)* a word problem reducing to a quadratic
8. *(stretch)* one differentiation question, to demonstrate topic extensibility

**Rubric shape** — three to five criteria, method-agnostic where possible:

```jsonc
{
  "question_id": "q2",
  "criteria": [
    { "id": "C1", "max": 1, "description": "Rearranged to a form suitable for solving" },
    { "id": "C2", "max": 2, "description": "Applied a valid solution method without loss or gain of roots" },
    { "id": "C3", "max": 2, "description": "Algebraic manipulation carried out correctly" },
    { "id": "C4", "max": 1, "description": "Stated all solutions" },
    { "id": "C5", "max": 1, "description": "Working is clear and logically ordered" }
  ]
}
```

Note C2's phrasing: it does not name a method, so completing the square and the formula both earn it.

### Handwritten student scripts — four to six per demo question, ~20 total

Written by different team members on plain white unlined paper, dark pen, photographed with a phone in good light. Deliberately cover:

| Script type | Purpose in the demo |
|---|---|
| Fully correct, tidy | Baseline; shows full marks awarded |
| Correct answer, no working | Shows method marks docked — a strong "this isn't answer-matching" moment |
| Sign error when factorising | The classic; tests misconception detection |
| Divided through by `x`, lost a root | The flagship symbolic-verification demo |
| Dropped the `±` | Common, easily explained |
| Sign error inside the discriminant | Tests arithmetic-level divergence detection |
| Alternative valid method (completing the square) | Tests method-agnostic marking |
| Genuinely messy handwriting | Tests the confirm-and-correct UX honestly |
| *(adversarial)* blank page, wrong question, doodle | Tests graceful failure |

For each: store the image, a hand-checked ground-truth transcription, and a hand-assigned ground-truth mark per criterion. **This ground truth is what your evaluation numbers are computed against — it is the difference between "it feels accurate" and "94% criterion-level agreement with a human marker."**

### Misconception catalogue — the pedagogical core

One JSON entry per misconception:

```jsonc
{
  "tag": "divided_by_variable_lost_root",
  "name": "Dividing both sides by a variable",
  "detection": "solution_set_shrank_between_steps",
  "why_students_do_it": "Dividing by x looks like the same simplification as dividing by a constant, but it silently discards the case x = 0.",
  "feedback_template": "You divided both sides by x, which removes the possibility that x itself is zero. Instead, move everything to one side and factorise.",
  "remediation_reference": "Lecture 4 §2 — the zero-product principle",
  "practice_template_ids": ["quad_factor_zero_root"]
}
```

Seven to ten of these covers quadratics thoroughly.

### Learning materials — deliberately small

Two to three pages of "lecture notes" as markdown with tagged sections (`#topic:quadratics/completing-the-square`), plus four to six worked examples. Enough to cite in feedback. **Do not** build a document corpus; you are not doing vector retrieval.

### Practice templates

Parameterised generators, one or more per misconception tag, each producing a question and a SymPy-verified answer:

```python
# quad_factor_zero_root: targets divided_by_variable_lost_root
# generates  a·x² = b·x  with integer a, b  →  roots {0, b/a}
```

---

## 16. Testing and evaluation strategy

Hackathon-appropriate: enough rigour to produce a credible number on a slide, not enough to consume your build time.

### Unit tests — where they genuinely pay off

- **`Verifier` (highest priority).** It is pure and deterministic, so it is cheap to test and expensive to get wrong. Table-driven tests: pairs of steps with a known equivalent/not-equivalent verdict; known lost-root cases; known parse failures. Aim for real coverage here and nowhere else.
- **`PracticeGenerator`.** Property test: for 200 random seeds, the generated question's stated answer satisfies the equation. This guarantees you never hand a student a broken problem.
- **LaTeX normalisation.** Known-awkward inputs (`\dfrac`, `\left(`, `\times`, `x^{2}` vs `x^2`) parse correctly.

### Contract tests

Every LLM response validates against its Pydantic schema. A schema violation is a test failure, not a runtime surprise. Snapshot the structured outputs for the six demo inputs at temperature 0 so you notice when a prompt change breaks something.

### End-to-end evaluation — the numbers for your slide

Against your ~20 hand-marked ground-truth scripts:

| Metric | Definition | Plausible target |
|---|---|---|
| **Transcription step accuracy** | % of steps transcribed exactly (post-normalisation) | ≥ 75% raw |
| **Steps needing correction** | Mean edits per script in the confirm UI | ≤ 2 |
| **Criterion-level mark agreement** | % of rubric criteria where AI mark = human mark, *given confirmed transcription* | ≥ 85% |
| **Total mark within 1** | % of scripts whose total is within one mark of the human's | ≥ 90% |
| **Misconception detection** | Precision/recall against hand-labelled tags | Report both honestly |
| **Symbolic verification correctness** | % of step verdicts correct | ~100% (it should be exact) |
| **Latency** | Upload → marks displayed | < 30 s |

Report the marking metrics *conditioned on confirmed transcription* — that is the honest measure of the marking engine, and it separates your two failure sources. Report the raw transcription number separately and without spin. Judges respect a team that reports 75% honestly far more than one claiming 99% with no methodology.

### Adversarial and robustness checks

Blank page · a photo of something that is not maths · the wrong question's working · correct answer with zero working · a script in pencil, badly lit · a step that will not parse · the network unplugged mid-run. Each should degrade visibly and gracefully — never a stack trace, never a silent wrong answer.

### Human evaluation — cheap and persuasive

Have one team member act as the lecturer and mark five scripts by hand, timing it. Then mark the same five through AIMS, timing it. **"Eleven minutes by hand versus ninety seconds with review"** is the single most persuasive number you can put on a slide, and it takes twenty minutes to obtain.

Also worth a slide: an honest limitations section. Stating what your system cannot do reads as maturity, not weakness.

---

## 17. Weaknesses, assumptions and missing considerations

### Unexamined assumptions in the current brief

1. **That OCR is a preliminary step rather than the product's central interaction.** Addressed above; this reframe is the most important change to make.
2. **That an LLM can be trusted to judge mathematical correctness.** It cannot, reliably. Hence symbolic-first.
3. **That RAG is needed.** At this corpus size it is not. §10.
4. **That the model solution defines the correct method.** Students use alternative valid methods constantly. Rubrics must be method-agnostic.
5. **That handwritten working is linearly ordered.** Real scripts have arrows, crossings-out, side calculations, and work in two columns. Your seeded scripts should be tidy and linear; state this scope limit openly rather than being caught by it.
6. **That marks are the deliverable.** For the stated problem — students not knowing what to practise — feedback and targeted practice are the deliverable. Marks are the lecturer's price of entry.

### Genuinely missing from the brief

- **Rubric authoring.** Assumed to exist. Fine for the MVP if you say so; be ready for the question.
- **The class-level view.** Your stated problem is large classes; a per-script tool does not visibly address it. Add it (§4, §12).
- **What happens to the marks afterwards.** Export? LMS? For the MVP, a printable feedback sheet is enough, but have an answer.
- **Automation bias.** If the AI proposes marks, lecturers will tend to accept them — including the wrong ones. Mitigations worth having: highlight low-confidence and disagreement cases, require an explicit approve action, log overrides. Being able to discuss this thoughtfully will distinguish you from every other team.
- **Fairness and appeals.** What does a student do who disagrees? The answer "a human made the final decision and the reasoning is recorded per criterion" is a good one — but only because you built the audit trail. Say it.
- **Cold-start effort.** Every question needs a model solution, a rubric and misconception tags. That is real lecturer work. Worth acknowledging, and worth a "future work" line about generating draft rubrics from a model solution.
- **Bias across handwriting styles.** Recognition quality varies by handwriting, which could systematically disadvantage some students. The human confirm step is your mitigation, and that is a strong answer — make it explicitly.

### Where the project is most likely to fail

Not the AI. **Integration and scope.** The two highest-value risk controls in this whole document are: define the JSON contracts before writing any logic, and freeze the feature list with 25% of your time remaining. Teams that do both ship a working demo. Teams that do neither have four excellent modules and nothing to show.

---

## Summary of recommended changes to the original plan

| Original | Recommended | Why |
|---|---|---|
| OCR → LaTeX → edit as a fallback | Confirm-and-correct as the **core interaction** | Converts the top risk into a designed feature |
| Traditional OCR + image preprocessing | Multimodal LLM, no preprocessing | Better results, a day saved |
| RAG over lecture notes and materials | Deterministic keyed retrieval over JSON seeds | More accurate at this scale, a day saved, no silent failures |
| LLM analyses working and assigns marks | **SymPy verifies first**, LLM maps verified facts to rubric | Removes the most damaging failure mode |
| LLM generates practice questions | Templates + SymPy verification | Never hands a student a broken question |
| Single-student marking flow | Add a class-level misconception dashboard | Connects the demo back to the stated problem |
| Topic unspecified | **Solving quadratic equations** | Best fit for step-level verification, handwriting simplicity and misconception richness |

---

---

## Addendum — revisions after clarification (2026-08-03)

**Answers received:** 2–4 days of build time · team mostly new to this stack · Anthropic API key with budget · free technology choice, but judged against a specific rubric (criteria still to be supplied).

These change three decisions.

### R1. Remove the JavaScript build toolchain

**Supersedes the frontend row of §8.** For a team new to the stack with three days, `npm` + Vite + TypeScript + React + CORS + two dev servers costs roughly a day of tooling friction and produces no demo value.

**Revised frontend:** FastAPI serves static `index.html` + `app.js` + `app.css`. Tailwind via CDN (`<script src="https://cdn.tailwindcss.com">`), KaTeX via CDN, Chart.js via CDN for the one bar chart. Vanilla JavaScript, `fetch`, no framework, no bundler, no build step.

Consequences:
- One language across the whole repo. Every team member can read and edit every file.
- No CORS configuration — same origin.
- One command starts everything: `uvicorn app.main:app --reload`.
- Edit, save, refresh. No build wait.
- Tailwind CDN still yields a polished interface; the visual result is indistinguishable to a judge.

**Also dropped:** MathLive (textarea + live KaTeX preview only), Recharts (Chart.js CDN instead), PDF export libraries (browser print-to-PDF).

### R2. The vertical slice must land on day one

With 2–4 days, Phase 1 in §13 becomes a day-one deadline, not a phase. One question, one handwritten script, image → transcription → confirm → SymPy verify → LLM marks, displayed. Ugly is acceptable; working is not optional.

Revised phase allocation for a 3-day build:

| Day | Target |
|---|---|
| **Day 0 (evening / first 3h)** | Contracts, repo, scaffold, full flow on fixtures. Everyone present. |
| **Day 1** | Vertical slice live on one real script. Offline fixture mode built. |
| **Day 2** | Six scripts, misconceptions, practice generation, feedback, override UI, class view. |
| **Day 3 (morning)** | Polish, evaluation numbers, slides. **Feature freeze at midday.** |
| **Day 3 (afternoon)** | Rehearsal only. Three timed run-throughs. Screen recording as backup. |

Cut order if behind schedule: class dashboard → practice generation → misconception catalogue depth → multi-question support. Never cut: the confirm step, symbolic verification, or offline mode.

### R3. Model selection and cost posture

Budget is available, so fixtures exist for *demo resilience*, not cost control.

- **Transcription:** `claude-sonnet-5` — fast, strong vision, cheap enough to iterate on prompts freely.
- **Marking and feedback:** `claude-opus-5` — the reasoning quality is visible in rubric justifications, which is what judges read.
- Temperature 0 everywhere. Structured outputs via tool use / JSON schema, validated with Pydantic.
- Cache every response for the six demo inputs; `DEMO_MODE=offline` replays them.

### Unchanged

Symbolic verification precedes and constrains the LLM · no vector RAG, keyed retrieval only · template-based SymPy-verified practice generation · contracts before logic · offline mode built on day two · quadratic equations as the topic · the four hard component boundaries in §7.

### Open

Judging criteria not yet supplied. They will not change the architecture, but they determine where the final day's polish goes — a social-impact rubric prioritises the class dashboard and impact framing; a technical-depth rubric prioritises making the symbolic-verification internals visible in the UI.

---

*Next step: written implementation plan.*
