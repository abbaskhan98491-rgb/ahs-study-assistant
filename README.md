# AHS Study Assistant

BS Allied Health Sciences, second semester revision from selected textbooks
and slides. Supports Physiology, Biochemistry, Anatomy, and English.

Run locally from this folder:

```cmd
python -m streamlit run app.py --server.fileWatcherType none
```

Store provider keys in `.streamlit/secrets.toml` or environment variables:
`GROQ_API_KEY`, `CEREBRAS_API_KEY`, `GEMINI_API_KEY`.
The app can start with any one provider configured. Never commit credentials.

The existing `rag_db/` is required. Compressed PDFs in `books_small/` display
source pages; use original text PDFs in `books/` when rebuilding the index.

Speed and reliability changes:

- Search model loads on the first request and remains cached.
- Topic Study uses ten chunks for broad topics and six for definitions/specific
  questions; MCQ retrieval keeps a 45-chunk pool, divided
  across requests of up to 15 chunks to reduce repeated input tokens.
- MCQ choices save immediately inside a Streamlit fragment, avoiding a full app rerun.
- Study answers and source selections survive page interactions.
- Current Cerebras/Groq models and stable Gemini Flash-Lite/Flash models are
  routed by recent valid response timings. There are no automatic benchmarks
  or parallel provider requests on normal study clicks.
- All providers use single REST attempts with bounded connection/read waits.
  Authentication, quota, retired models, timeouts and invalid responses receive
  appropriately scoped cooldowns. Retry-After is honored; HTTP 402 pauses the
  affected credential for at least one hour without requesting paid access.
- A provider response must pass MCQ source/page/option validation before it can
  win or teach the router its speed. Definitions and full topic explanations
  retain their separate scope and output budgets.
- Each routing call has a 60-second scheduling budget, with at most five
  attempts of up to 25 seconds. A whole MCQ generation shares a 150-second
  budget across batches and preserves a partial set for continuation. Socket
  timeouts bound connection and inactivity, not a strict cancellable wall clock.
- Malformed quiz output, invalid source references, duplicate options, and
  negative questions with combining options are rejected. Component-list
  questions also reject distractors that merely reorder the same members;
  explicit sequence questions retain their meaningful order differences.
  Spinal-root questions reject duplicated anterior/ventral or posterior/dorsal
  answer names. This narrow check does not merge directional adjectives globally.
  Ganglion-count stems must identify original segmental components or fused
  named groups; bare counts are omitted rather than treating both as the same.
- Quiz generation has a ten-batch limit and stops after provider failure.
  A partial quiz is clearly labeled; insufficient text cannot guarantee 40
  distinct supported questions.
- Diagram output chooses the smaller of PNG and JPEG, with a bounded cache.

Offline regression checks (no AI calls or database writes):

```cmd
python -m unittest test_study_assistant -v
python -m py_compile app.py study_utils.py test_study_assistant.py
```

Tests cover UI state, instant MCQ feedback and selection reset, source isolation, truncated
JSON, invalid options and references, repeats, rate-limit fallback, and
45-chunk coverage for a simulated 40-question paper. They do not establish
live AI response times or the factual quality of generated questions.

October 2026 loading improvements:

- Quiz requests now target 16 questions per batch, with two spare candidates.
  Explanations use one short sentence and output budgets scale with batch size.
- Complete quizzes are reused for one hour in the same session (up to six topics).
  Select "Make fresh questions" to generate another set. Cached quizzes bypass
  model loading, retrieval and AI calls; partial quizzes are never cached.
- Source-page images render only after "Load selected page", one page at a time.
  After a study answer, a few retrieved PDF pages are inspected for relevant
  figures. Page previews use 1.5x zoom rather than 2.2x; PyMuPDF imports on demand.
- The app prefers books_optimized/ and falls back to existing source files.
  Run `python optimize_documents.py` to create verified smaller display copies
  from books_small/ while retaining originals, page counts and text layers.
  This optional tool requires PyMuPDF >= 1.26.1.
- The repository includes the five smaller display copies. The Physiology and
  Snell textbooks use the existing books_small/ files when their local optimized
  copies are absent; those two copies save no meaningful space and are ignored.
  PDF files are marked binary in Git to preserve their exact bytes.

PDF compression improves display/loading; AI latency still depends on the
provider, quota and question validity. Offline checks do not measure live AI speed.

Optional API speed measurement:

```cmd
python benchmark_providers.py
```

This explicit command sends one identical fictional MCQ to each configured
provider, at most three completion requests. It sends no textbook or student
material and validates the known answer. Timings and temporary health scopes
are saved for one hour in the ignored `tmp/provider-speed-profile.json`; raw
keys, prompts, responses and provider error bodies are not saved. Credential
fingerprints keep measurements separate when a key changes. Actual valid
study/MCQ calls continue updating the session's timing preference per task.

The short local probe on 10 October 2026 measured Groq GPT-OSS 20B at 0.727s and
Gemini 3.5 Flash-Lite at 1.391s. Cerebras returned HTTP 402 and was paused.
These timings describe one small synthetic exercise, not a 40-question set
or a guarantee of future response time.

A live nervous-system check produced all 40 questions in 65.1 seconds through
Gemini, with immediate explanation on selection. Full topic study and the
one-sentence "Define neuron" flow were also checked in Chrome. A second fresh
40-question set took 52.7 seconds; these observations are not speed guarantees.
The later check with list/root ambiguity filters produced 40 questions in 69.3s.

Provider regressions: `python -m unittest test_provider_router test_provider_transport test_benchmark_providers test_mcq_validation test_study_assistant -q`.

Choose a subject and Book/Slides, select a searchable syllabus suggestion or
type any topic/specific question, then use Topic Study or Generate 40 MCQs.
Islamic Studies is excluded. There are no unit, chapter, or coverage selectors.
Answers come from the selected
indexed textbook or slides. Availability depends on what those sources cover.

Detailed syllabus coverage:

- The supplied KMU second-semester syllabus (2021-22) remains imported in
  syllabus_details.json. Topic suggestions load locally for the selected subject;
  there are no unit/chapter controls. Requests use the editable question field.
- The standalone syllabus helper can still build scopes and the retrieval
  helper can merge passages across them; neither adds controls to the page.
- The mapping contains 175 topic entries and 401 theory/practical learning
  outcomes across the four subjects. Practical / OSPE has its own section.
  General affective/attendance/conduct rows are counted in the import audit,
  but are not listed as medical study topics. Islamic Studies is excluded.
- Each outcome retains its PDF page and row number. Nine blank Physiology
  domain cells are classified from their theory or demonstration context and
  flagged domain_inferred in the data. Original curriculum wording is retained.
- To rebuild the mapping: python import_syllabus.py "PATH_TO_SYLLABUS_PDF".
  The importer checks table columns by their domain labels and rejects unknown
  rows instead of silently skipping them. Requires the same supplied 44-page PDF.
- Syllabus mapping does not pre-generate notes or questions, establish factual
  correctness, or guarantee a textbook covers every objective. Answers must
  identify material not supported by the retrieved selected source.

Simple study interface:

- Subject/source, searchable topic suggestions, editable topic input,
  fresh-question option and the two action buttons
  stay visible, including after a result. There is no hidden setup panel or
  workspace selector. The latest action displays study notes or MCQs.
- All MCQs appear in one scrolling list. Selecting an option immediately shows
  correct/incorrect, the correct answer, a short explanation and source reference.
  There is no score, submit, retry, previous/next or five-question pagination.
- Partial MCQ sets show the exact count out of 40. Complete remaining questions
  keeps existing valid questions and answers while requesting missing ones.
  Invalid output can advance to another context window; actual provider failure
  still stops retries. A narrow source cannot guarantee 40 distinct questions.
- UI checks: `python -m unittest test_study_assistant test_quiz_ui -q`.
  Checks cover all 40 questions on one page, immediate feedback without network
  requests, answer preservation across theme/view changes, new-set reset,
  partial-set append, and resuming after empty retrieval.
- Suggestions include the subject's topic titles and theory/practical subtopics.
  Type a few letters in "Find a syllabus topic" to search: Streamlit's native
  fuzzy matching allows "ner" to match "Neuron". Selecting a suggestion fills
  the question field; editing it keeps full control over a specific question.
  Changing subject clears the selection and switches the suggestions.
- The catalogue uses lazy local JSON loading and a per-subject cache. Searching
  or selecting suggestions does not open PDFs, load retrieval resources or make
  an AI call. Requires Streamlit >= 1.65.0 for the fuzzy filter mode.
- Suggestion checks: `python -m unittest test_topic_suggestions test_study_assistant -q`.

Study depth and MCQ answer positions:

- A bare topic requests a full teaching explanation with useful headings and
  connected paragraphs. An explicit "define" request asks for a definition in
  one to three sentences. Types/functions/steps/comparisons stay focused and
  explain the requested material. All answers remain limited to source passages.
  References are requested once at the end rather than after every point.
- New MCQ options are shuffled locally while correct indices are updated. Forty
  safely reorderable questions have ten correct answers at each A/B/C/D position,
  in random order. Combining/letter references are expanded to their original
  option meanings before reordering; ambiguous cases retain their safe order.
- Completed caches are upgraded once without AI calls. Current saved selections
  are mapped to their equivalent option text. Appended questions leave the
  existing prefix unchanged; answer choices now display A/B/C/D labels.
  Provider labels such as "A text" are removed before reordering, so choices
  do not display two labels. Factual letters such as "B cells" are preserved.
- Gemini fallback keeps all returned answer text parts, excluding thought parts.
  A locally cached search model is loaded without repeated network checks.
- Checks: `python -m unittest test_study_format test_mcq_order test_topic_suggestions test_study_assistant test_quiz_ui test_diagram_utils -q`.
- Chrome verification confirmed searchable syllabus suggestions, a full nervous
  system explanation, and a one-sentence answer for "Define neuron".
  A live nervous-system set produced 40 questions; selecting each first choice
  confirmed ten correct answers at each A/B/C/D position with no duplicate labels.

First-load layout and instant practice feedback:

- Initial desktop setup shows the simple controls immediately, with an empty
  topic input. The original soft pink styling and title are restored; the
  masthead and footer stay compact.
  The compact desktop rules target widths >= 900px. The entire setup and footer
  fit the tested 1280x537 Chrome viewport without vertical scrolling. There is
  no overflow lock or clipped-content height cap.
- Opening saved notes or MCQs switches to the normal scrolling results layout.
  Switching to a source without a saved result restores the initial setup.
  Small/mobile screens remain scrollable to preserve readable controls.
- Selecting an MCQ option immediately displays the correct answer, explanation
  and available reference. Feedback is drawn from the existing question payload
  and makes no new AI request. Selection, view changes and themes preserve it.
- Functional tests verify controls and transitions alongside desktop browser
  inspection. Smaller/mobile screens retain natural scrolling for readability.

Relevant source diagrams:

- Diagram choices are checked against the exact selected PDF and retrieved pages.
  A page needs a sizeable figure and a matching caption, or a matching heading
  on a diagram-heavy slide. Tiny logos, text-only slides and unrelated figures
  do not qualify merely because metadata says the page contains an image.
- There is no page-distance or unrelated-slide fallback. Matching is conservative;
  image-only pages without a readable caption/heading may be omitted. A matched
  source page is a preview of the actual PDF, not a generated illustration.
- Checks are cached; first opening or typing a topic does not open any PDF.
  Regression checks: `python -m unittest test_study_assistant test_quiz_ui test_diagram_utils -q`.
