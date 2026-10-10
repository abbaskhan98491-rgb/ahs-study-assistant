# AHS Study Assistant — Master Prompt

Paste this whole file at the start of a new AI chat before asking for any
change to this app. It says what the app is, what I want from it, and the
rules that must never be broken.

---

## 0. Who I am and how to talk to me

- I am Abbas Khan. I study BS Allied Health Sciences, 2nd Semester, at
  Khyber Medical University (KMU), Pakistan.
- I built this app for myself and my class.
- I am not a programmer. I can run commands in Windows cmd if you give me
  the exact line to paste. I am slow at copy-paste, so do not ask me to
  copy large blocks of code.
- Talk to me directly. No praise, no long introductions. If I am wrong,
  say so and say why. If something cannot be done, say that instead of
  giving me a half answer.
- Write in simple English, or Roman Urdu mixed with English. Short
  sentences. Bullet points over long paragraphs.
- When you claim something is fixed, show me the proof: the numbers, the
  test output, or the file you changed.

---

## 1. What the app is

A Streamlit web app that studies from my own course books and slides.

- Repo folder on my PC: `C:\projects\ahs-study-assistant`
- Live: https://ahs-study-assistant-abbas.streamlit.app/
- Main file: `app.py` (one file, about 1,300 lines)

It has two modes:

1. **Topic Study** — I type a topic, it answers from the book, with the
   book name and page number, and shows the diagram page if there is one.
2. **Generate MCQs** — I type a topic, it makes one scrolling list of MCQs.
   Picking an option immediately shows right/wrong, the correct answer and
   a short explanation. No quiz submission, score or pagination.

How it works inside:

- The books are cut into pieces ("chunks") and stored in ChromaDB at
  `rag_db/` (collection `semester_books`, 7,333 chunks).
- Search uses sentence-transformers `all-MiniLM-L6-v2`.
- Diagram pages are rendered from the PDFs in `books_small/` with PyMuPDF.
- The text is written by an LLM, which only sees the chunks that were
  pulled from my book. It is not allowed to use its own knowledge.

---

## 2. The hard rules — never break these

1. **Never put an API key in `app.py` or in any file that goes to GitHub.**
   Keys live only in `.streamlit/secrets.toml`, which is in `.gitignore`.
   I have ONE key per provider and I cannot create new ones. Losing a key
   is not acceptable.
2. **Never print, echo, or commit a key**, not even part of one.
3. **Never overwrite `.streamlit/secrets.toml`.** My keys are in it.
4. **Check `.gitignore` actually works** before any commit that could touch
   secrets: `git check-ignore -v .streamlit/secrets.toml` must exit 0.
5. **Back up `app.py` before a big change**, e.g.
   `app_BACKUP_<what-changed>.py`, and keep it out of git.
6. **Never invent facts.** Every question, option, answer and explanation
   must come from the retrieved book text.
7. Do not add new Python packages unless there is no other way. The app has
   to keep installing on Streamlit Cloud free tier.

---

## 3. Where the content comes from

I pick a Subject and a Source in the Study Panel. That picks exactly ONE
file, and only that file's chunks are searched.

| Subject | Source | File in the database | Chunks |
|---|---|---|---|
| Physiology | Book | `Essentials of Medical Physiology (6 Ed)(book).pdf` | 1,823 |
| Physiology | Slides | `Physiology-Slides.pdf` | 1,269 |
| Biochemistry | Book | `Satyanarayana-biochemistry-pdf-free.pdf` | 1,609 |
| Biochemistry | Slides | `Biochemistry-Slides.pdf` | 314 |
| Anatomy | Book | `Snells-clinical-anatomy-by-regions-10 ed.pdf` | 1,561 |
| Anatomy | Slides | `Anatomy-slides-pdf.pdf` | 380 |
| English | Slides | `English-Slides.pdf` | 377 |

Rules:

- The subject I picked must be named in the prompt. The model must never be
  asked to "guess the subject from the context".
- The model must be told the exact file name, and the page reference it
  writes must name that file.
- Content from any other subject is a bug, not a bonus.
- English has slides only, no book. Biochemistry slides are small (314).
  On those two, 40 questions is near the limit of the material.
- **Islamiat is not supported.** There is no Islamiat PDF in the database,
  and the embedding model is English-only, so Urdu would need a different
  model and a full rebuild of `rag_db`. Do not pretend otherwise.

---

## 4. MCQs — what I want

### The goal

Questions that look like the ones **my teachers write from these books**,
not questions from an international exam bank. I gave you my real KMU past
papers (Anatomy-II, Biochemistry-II, English, Physiology) so you could
learn the style. The papers were for the STYLE. They were never a target
for how many questions to make.

### Count

- **40 questions per topic.** Not 70, not 30.
- If a topic runs out of material, loosen the repeat filter and still give
  me 40. Do not hand back 31.

### Style — every subject

- Stems are SHORT, 8 to 20 words.
- **No patient stories and no case histories.** Never "A 55-year-old man
  presents with...". My papers have none.
- Most stems are an unfinished sentence that the options complete.
- Options are SHORT, one to five words.
- All four options are the same kind of thing: all enzymes, or all bones,
  or all tenses, or all numbers. Never mixed.
- About 1 in 3 questions ends with a combining option: "All of the above",
  "Both A and B", "None of the above". Sometimes it is correct, sometimes
  not.
- Number options stay close together: 6, 7, 8, 10 — never 2, 8, 50, 900.
- About 1 in 6 is negative, using the real wordings:
  "All of the following are ... Except?", "Which of the following is NOT",
  "... comprises of all EXCEPT:", "Which of the following, regarding X,
  is INCORRECT?"
- Never put a combining option inside a negative/EXCEPT question. "All of
  the following are essential fatty acids EXCEPT: ... Both A and B" is
  broken logic and must never happen.
- Spread the correct answer across A, B, C and D.

### Style — Anatomy and Physiology

Blank at the end; blank in the middle; describe-then-name; supply, origin,
insertion, relation; statement style where the four options are short
sentences. Options are structures: nerves, muscles, bones, arteries, veins,
spaces.

### Style — Biochemistry

Name the enzyme, product, site or coenzyme; counts and values ("how many
cycles of beta oxidation", "how many ATP"); inhibition and regulation; name
the disease then ask its cause; clinical enzymology and markers.

### Style — English

Language questions ONLY. No medicine, no biology. Grammar transformation
with four full sentences as options; direct and indirect narration; identify
the phrase or clause in quoted words; report, letter and memo terminology;
counting ("there are ......... parts"); word meaning and word form; essay,
listening and presentation.

### No repeats — this is the part that broke before

A real set of 40 I generated had 12 repeats. Rules now:

- Never ask the same fact twice, even in different words. "Which enzyme
  hydrolyses triacylglycerol in adipose tissue" and "The stored fat in
  adipose tissue is hydrolysed by" are the SAME question.
- The same correct answer may be right at most twice in the whole set.
- Code must filter repeats, not just ask the model nicely. The filter
  compares, after cutting word endings:
  - the question wording,
  - all four options,
  - the correct answer,
  and drops a question when the wording is nearly the same, OR the correct
  answer is the same and the subject matches, OR the wording is close and
  the options mostly match.
- Keep the context wide (45 chunks) so there is enough material for 40.
- Prove the filter works on a real set before telling me it is fixed.

### Difficulty

2nd semester level, from my book. A question like "which amino acid is
coded by the UGA stop codon" (selenocysteine) is outside my syllabus and
must not appear. If it is not in the retrieved text, it is not a question.

---

## 5. Answers — what I want

- The answer comes from the selected subject and the selected file only.
- Topic Study answers are written like an exam answer: clear headings or
  bullets, the key points (what it is, types, functions, steps, relations),
  and the book name with page number for the main points.
- If I type one word ("mandible", "glycolysis"), explain that topic. Do not
  refuse it as "too broad".
- Only say it is missing if the topic really is not in the retrieved text.
- For MCQs, selecting an option immediately shows right/wrong, the correct
  answer, a short explanation, and the page it came from.
- English gets an English tutor voice, not a medical one.

---

## 6. Speed or quality

**Quality first. I will wait.**

- 40 good questions in 1 to 3 minutes is fine.
- 40 questions in 20 seconds with 12 repeats is not fine.
- Always show a progress bar with real numbers: "Made 23 of 40 questions...".
- Keep the answer mode fast — a few seconds — because I use it while reading.

Current settings that produce this:

```
TOP_K = 6              # chunks for Topic Study
MCQ_CONTEXT_K = 45     # chunks for making MCQs
MCQ_TOTAL = 40
MCQ_BATCH = 10         # questions per API call
GROQ_MODEL     = "llama-3.3-70b-versatile"   # answers: slower, better
GROQ_MCQ_MODEL = "llama-3.1-8b-instant"      # MCQs: faster, bigger free quota
```

Providers run in order and the app must never stop because one is busy:

1. Groq — every key I have, tried one after another
2. Cerebras
3. Gemini

The app must start if ANY provider has a key, not only Groq.

---

## 7. UI and UX

The look is "Sanrio" — soft pink, rounded, friendly. Keep it. Do not
replace it with a plain or corporate theme.

- Palette: `--pink-900:#9d1b5c`, `--pink-700:#c9256f`, `--pink-500:#ff6fae`,
  `--pink-300:#ffb3d4`, `--pink-100:#ffe4f0`, `--pink-50:#fff5fa`,
  card `#ffffff`, border `#f6d9e7`, soft pink page gradient.
- Rounded corners (11–14px), thin pink borders, soft shadows, no hard lines.
- Buttons are a pink gradient with white text.
- Streamlit's own menu, header and footer are hidden.

Layout:

- Subject (dropdown), Study from (Book / Slides radio), Dark mode toggle,
  one text box for the topic, and two equal buttons: **Topic Study** and
  **Generate MCQs**. Keep these controls visible, with a compact header and footer.
- One searchable suggestion list for the selected subject's topics and subtopics.
  Typing a few letters (e.g. "ner") filters the list, and selecting a suggestion
  fills the editable question box. Custom questions must still work.
- No unit, chapter, coverage or workspace selectors. Suggestions must use local
  syllabus data and stay fast without loading PDFs, the search model or AI.
- MCQ cards: "QUESTION 7" in small pink capitals, the question in bold,
  options as radio buttons that look like pills, nothing pre-selected.
- All MCQs on one page; scrolling is fine. No Next 5, quiz score, submit or retry.
- Selecting an option immediately shows right/wrong, the correct answer,
  a short explanation and the page reference.
- Shuffle and balance correct answers across A/B/C/D locally; updating positions
  must preserve the actual correct answer and combining-option meanings.
- A bare topic gets a full, clear teaching explanation. "Define" requests get
  only the definition; specific aspects get a focused explanation. Keep source
  references together at the end rather than interrupting every point.
- Diagram pages must contain a relevant figure for the typed topic. Do not
  treat every slide or logo-bearing page as a diagram or fall back to unrelated pages.
- Footer: "Created by Abbas Khan · BS Allied Health Sciences · 2nd
  Semester", with WhatsApp 0345-9059934, Email, TikTok and Instagram links.
- Dark mode must work and must be reachable even when the Study Panel is
  hidden.
- It must look right on a phone. My classmates open it on phones.

Behaviour:

- Starting a new MCQ set must clear the previous set's selected answers,
  so the new questions open without old answers already ticked.
- Errors are shown as one short line, not a Python traceback.

---

## 8. How to give me the code

- **Write the file directly into `C:\projects\ahs-study-assistant`.** Do
  not paste a long block and ask me to copy it.
- After writing, verify it landed: compare the file size and checksum, and
  run a syntax check. A write can silently land as an old version — check,
  do not assume.
- Change one thing at a time and tell me what changed in plain words.
- Run a static check (`pyflakes`) before telling me it is done.
- Comments in the code should be plain English that explains WHY, in the
  same calm style as the rest of the file.

---

## 9. How I deploy

```
cd C:\projects\ahs-study-assistant && git push
```

- I run this myself in Windows cmd. Automated shells here have no GitHub
  login, so pushing from your side will fail.
- Streamlit Cloud redeploys from GitHub by itself after the push.
- `rag_db/` is committed on purpose — the live app needs it.
- **If the live app does not match my PC, the reason is almost always that
  I have not pushed yet.** Check `git log origin/main` before blaming the
  code.
- Streamlit Cloud needs the same keys in its own Secrets box:
  `GROQ_API_KEY`, `CEREBRAS_API_KEY`, `GEMINI_API_KEY`.

---

## 10. Traps that already cost me time

- `'pip' is not recognized` on my PC → use `python -m pip`, and
  `python -m streamlit`.
- Running locally throws 50+ `No module named 'torchvision'` errors →
  start with `--server.fileWatcherType none`.
- `.gitignore` had Windows line endings and no last newline, so appending a
  line joined it to the previous one and `secrets.toml` stopped being
  ignored. Always rewrite the whole file, and verify with `git check-ignore`.
- Git in an automated Linux shell leaves `.lock` files behind that break my
  next git command. Clear them.
- A file written to my PC can come back as the OLD version. Writing to a
  new name and then renaming works. Always verify the checksum.
- Do not "fix" things I did not ask about in the same change. Tell me, and
  let me decide.

---

## 11. Still open — ask me, do not guess

- English has no book, only slides (377 chunks). To get better English
  questions I would need to add an English book PDF and rebuild `rag_db`.
- Islamiat is not in the app at all and cannot be added without changing
  the embedding model.
- Biochemistry slides are small (314 chunks); 40 questions there may repeat.
- Whether `rag_db` (70 MB) should stay in git, or move to a release file.
