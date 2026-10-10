"""
Medical Study Assistant - Web App (Streamlit)
Two modes: Ask a Question  +  Practice MCQs (Sanrio-styled)
RUN LOCALLY:  streamlit run app.py
"""

import os
# Keep numerical libraries from reserving many thread stacks on small PCs.
# Explicit settings supplied by the user still take precedence.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "2")
import re
import time
from study_utils import parse_mcqs, compact_context, friendly_error
import streamlit as st
from ui_theme import LIGHT_CSS as SANRIO_CSS, DARK_CSS
from quiz_ui import render_mcqs
from diagram_utils import select_diagram_pages
from topic_suggestions import get_topic_suggestions
from mcq_order import balance_mcq_options
from study_format import classify_study_request, build_study_instructions
from provider_router import route_completion, load_speed_profile, GROQ_STUDY_MODEL, GROQ_MCQ_MODEL

# ---------------- SOURCES: subject -> Book / Slides file names ----------------
# These must match the exact PDF file names in the books/ folder.
SOURCES = {
    "Physiology": {
        "Book": "Essentials of Medical Physiology (6 Ed)(book).pdf",
        "Slides": "Physiology-Slides.pdf",
    },
    "Biochemistry": {
        "Book": "Satyanarayana-biochemistry-pdf-free.pdf",
        "Slides": "Biochemistry-Slides.pdf",
    },
    "Anatomy": {
        "Book": "Snells-clinical-anatomy-by-regions-10 ed.pdf",
        "Slides": "Anatomy-slides-pdf.pdf",
    },
    "English": {
        "Slides": "English-Slides.pdf",
    },
}


# ---------------- CONFIG ----------------
BOOKS_DIR = "books_optimized" if os.path.isdir("books_optimized") else ("books_small" if os.path.isdir("books_small") else "books")
DB_DIR = "rag_db"
COLLECTION_NAME = "semester_books"
EMBED_MODEL = "all-MiniLM-L6-v2"
TOP_K = 6
MCQ_CONTEXT_K = 45          # wide context, else 40 questions start repeating
MCQ_TOTAL = 40              # 40 questions per topic
MCQ_BATCH = 16               # generate this many per API call
GROQ_MODEL = GROQ_STUDY_MODEL
ZOOM = 1.5

# Credentials belong in Streamlit secrets or environment variables.

def _looks_real(v):
    """Ignore placeholders without making assumptions about key letter case."""
    v = (v or "").strip()
    if len(v) < 12:
        return False
    if "PASTE" in v.upper() or "YOUR-KEY" in v.upper():
        return False
    return True


def _collect_groq_keys():
    """Gather every Groq key available, in the order we should try them."""
    found = []
    # 1. Streamlit Cloud secrets (GROQ_API_KEY, GROQ_API_KEY_2, GROQ_API_KEY_3 ...)
    try:
        for name in ["GROQ_API_KEY", "GROQ_API_KEY_2", "GROQ_API_KEY_3",
                     "GROQ_API_KEY_4", "GROQ_API_KEY_5"]:
            try:
                v = st.secrets[name]
            except Exception:
                v = ""
            if v:
                found.append(str(v).strip())
    except Exception:
        pass
    # 2. Environment variable
    v = os.environ.get("GROQ_API_KEY", "")
    if v:
        found.append(v.strip())
    # drop blanks, placeholders and duplicates, keep the order
    return list(dict.fromkeys([k for k in found if _looks_real(k)]))


GROQ_KEYS = _collect_groq_keys()
GROQ_API_KEY = GROQ_KEYS[0] if GROQ_KEYS else ""

# ---- OTHER PROVIDERS (ranked by validated response speed) ----


def _one_key(secret_name):
    """Look for a key in Streamlit secrets, then the environment.
    Placeholder text is ignored, so a half-filled file costs no time."""
    try:
        v = st.secrets[secret_name]
        if _looks_real(v):
            return str(v).strip()
    except Exception:
        pass
    v = os.environ.get(secret_name, "")
    if _looks_real(v):
        return v.strip()
    return ""


CEREBRAS_API_KEY = _one_key("CEREBRAS_API_KEY")
GEMINI_API_KEY = _one_key("GEMINI_API_KEY")

# ---------------- LLM CALL WITH AUTOMATIC FAST FALLBACK ----------------
def call_llm(prompt, groq_client, max_tokens=2000, temperature=0.3, model=None,
             *, task=None, validator=None):
    """Prefer measured valid responses; never benchmark on a study click."""
    request_task = "mcq" if model == GROQ_MCQ_MODEL else task or "topic"
    if "ai_router_state" not in st.session_state:
        st.session_state["ai_router_state"] = load_speed_profile()
    result = route_completion(
        prompt, groq_keys=GROQ_KEYS, cerebras_key=CEREBRAS_API_KEY,
        gemini_key=GEMINI_API_KEY, state=st.session_state["ai_router_state"],
        task=request_task, max_tokens=max_tokens, temperature=temperature,
        validator=validator,
        deadline=st.session_state.get("mcq_request_deadline") if request_task == "mcq" else None,
    )
    st.session_state["last_provider_model"] = result.model
    st.session_state["last_api_seconds"] = result.elapsed
    return result.text, result.provider


# ---------------- CACHED LOADERS ----------------
@st.cache_resource
def load_model():
    # Avoid importing PyTorch until the student actually starts studying.
    from sentence_transformers import SentenceTransformer
    try:
        # A cached model does not need repeated network checks on every restart.
        return SentenceTransformer(EMBED_MODEL, local_files_only=True)
    except OSError:
        return SentenceTransformer(EMBED_MODEL)


@st.cache_resource
def load_collection():
    import chromadb
    client = chromadb.PersistentClient(path=DB_DIR)
    return client.get_collection(COLLECTION_NAME)


@st.cache_data(max_entries=24, ttl=3600)
def render_page(book, page):
    import pymupdf as fitz
    path = os.path.join(BOOKS_DIR, book)
    if not os.path.isfile(path):
        path = next((os.path.join(folder, book) for folder in ("books_small", "books")
                     if os.path.isfile(os.path.join(folder, book))), path)
    with fitz.open(path) as doc:
        pix = doc[page - 1].get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM))
        # Text pages often compress better as PNG; diagrams may favor JPEG.
        png = pix.tobytes("png")
        jpeg = pix.tobytes("jpeg", jpg_quality=80)
        img_bytes = min((png, jpeg), key=len)
    return img_bytes


@st.cache_data(max_entries=128, ttl=3600, show_spinner=False)
def get_relevant_diagram_pages(question, chunks, metas, selected_book):
    """Check a few retrieved source pages; never invent a diagram reference."""
    path = os.path.join(BOOKS_DIR, selected_book)
    if not os.path.isfile(path):
        path = next((os.path.join(folder, selected_book) for folder in ("books_small", "books")
                     if os.path.isfile(os.path.join(folder, selected_book))), path)
    return select_diagram_pages(question, chunks, metas, selected_book, path)


# ---------------- CORE: retrieve ----------------
@st.cache_data(ttl=300, max_entries=128, show_spinner=False)
def retrieve(question, selected_book, _model, _collection, k, focus_topics=()):
    searches = list(focus_topics) or [question]
    q_emb = _model.encode(searches).tolist()
    per_search = k if len(searches) == 1 else min(6, max(2, (k + len(searches) - 1) // len(searches)))
    args = {"query_embeddings": q_emb, "n_results": per_search}
    if selected_book != "Both / All books":
        args["where"] = {"book": selected_book}
    results = _collection.query(**args)
    if len(searches) == 1:
        return results["documents"][0], results["metadatas"][0]
    chunks, metas, seen = [], [], set()
    # One batched embedding/query, then round-robin source passages across topics.
    for rank in range(per_search):
        for docs, metadata in zip(results['documents'], results['metadatas']):
            if rank >= len(docs):
                continue
            text, meta = docs[rank], metadata[rank]
            identity = (meta['book'], meta['page'], text)
            if identity not in seen:
                chunks.append(text)
                metas.append(meta)
                seen.add(identity)
            if len(chunks) >= k:
                return chunks, metas
    return chunks, metas


# ---------------- MODE 1: Q&A ----------------
def answer_question(question, subject, selected_book, model, collection, groq_client, focus_topics=()):
    intent = classify_study_request(question)
    base_k = 10 if intent == "topic" else TOP_K
    context_k = min(45, max(base_k, len(focus_topics) * 2))
    chunks, metas = retrieve(question, selected_book, model, collection, context_k, focus_topics)
    if not chunks:
        return ("Nothing on that was found in this source. Try the other "
                "source (Book / Slides) in the Study Panel, or word the "
                "topic the way the book words it."), []

    context = compact_context(chunks, metas)
    tutor = "an English language tutor" if subject == "English" else "a medical study tutor"
    prompt = f"""You are {tutor} teaching {subject} to a BS Paramedics student.
Answer the student's question using ONLY the {subject} context below, which
comes from "{selected_book}". Do not use any other subject, and do not use
your own knowledge.

{build_study_instructions(question, intent)}
- A single topic name is a valid request for full teaching. Do not dismiss it as too broad.
- Only say the answer is missing if the topic is absent from the supplied context.

{subject} CONTEXT (from {selected_book}):
{context}

QUESTION: {question}

ANSWER:"""
    output_budget = {"definition": 600, "specific": 1800, "topic": 2500}[intent]
    answer, provider = call_llm(prompt, groq_client,
                                max_tokens=output_budget, temperature=0.25, task=intent)
    st.session_state["last_provider"] = provider

    diagram_pages = ([] if intent == "definition"
                     else get_relevant_diagram_pages(question, chunks, metas, selected_book))
    return answer, diagram_pages


# ---------------- MODE 2: MCQ generation ----------------
# ---------------- MCQ STYLE RULES (from the real KMU past papers) ----------------
# The student picks a subject in the app. Only that subject's rules are put in
# the prompt, so an English paper never sees the Biochemistry rules.

MCQ_RULES_GENERAL = """- Stems are SHORT, usually 8 to 20 words.
- There are NO patient stories and no case histories anywhere. Never
  write "A 55-year-old man presents with..." The real papers have none.
- Most stems are an unfinished sentence that the options complete.
- Options are SHORT, usually one to five words.
- All four options must be the same kind of thing: all enzymes, or all
  bones, or all tenses, or all numbers. Never mix kinds.
- In about one question out of three, make the last option a combining
  one: "All of the above", "All of these", "Both A and B", or
  "None of the above". Sometimes it is correct, sometimes it is not.
- For number questions keep all four values close together, for example
  6, 7, 8, 10 - never 2, 8, 50, 900.
- About one question in six must be NEGATIVE. Use the real wordings:
  "All of the following are ... Except?"
  "Which of the following is NOT ..."
  "... comprises of all EXCEPT:"
  "Which of the following, regarding X, is INCORRECT?"
- Never repeat the same option twice in one question.
- Spread the correct answer evenly across A, B, C and D.

NO REPEATS - this matters most:
- Never ask the same fact twice, not even in different words. "Which enzyme
  hydrolyses triacylglycerol in adipose tissue" and "The stored fat in adipose
  tissue is hydrolysed by" are the SAME question and only one may appear.
- Never let the same correct answer be right more than twice in the whole set.
- Before writing each question, pick a fact from the context that no earlier
  question has used. Walk through the context and cover different parts of it.
- Do NOT put a combining option ("All of the above", "Both A and B",
  "None of these") in a NEGATIVE or EXCEPT question - it makes the logic
  break. Use combining options only in ordinary questions."""

MCQ_RULES_SCIENCE = """1. Blank at the end:
   "Filum terminale is attached to which segment of spinal cord,"
   "The name thenar eminence is given to short muscles of the,"
2. Blank in the middle:
   "The ......... is triangular and occupies the central area of the palm."
   "The ......... gland is the largest salivary gland?"
3. Describe first, then name it:
   "The largest bone of the foot and forms the prominence of the heel is,"
   "A strong membrane that unites the shafts of the radius and the ulna is"
4. Supply, origin, insertion, relation:
   "What is the nerve of the anterior compartment of the thigh?"
   "Pectoralis minor originates from"
   "Which nerve supplies the heart?"
5. Statement style, where the four options are short sentences:
   "Regarding the femoral artery:"   "The sciatic nerve:"
6. Negative, as described in Part 1.
Options are structures: nerves, muscles, bones, arteries, veins, spaces."""

MCQ_RULES_BIOCHEM = """1. Name the enzyme, product, site or coenzyme:
   "The synthesis of urea occurs in"
   "Uric acid is end product of"
   "The precursor for glycogen synthesis is"
2. Count or value - very common in the real paper:
   "A fatty acid with 14 carbons will undergo how many cycles of beta oxidation"
   "The first step of urea cycle consumes how many ATP"
   "One FADH2 is equal to"
3. Inhibition and regulation:
   "Phosphofructokinase is"
   "Carnitine acyltransferase I is inhibited by"
4. Name the disease or defect, then ask its cause. Do NOT describe the
   symptoms of an unnamed patient:
   "Albinism is caused by the deficiency of"
   "McArdle disease is a condition in which:"
   "An important etiological factor in kwashiorkor is"
5. Clinical enzymology and markers:
   "An enzyme marker of acute pancreatitis is"
   "Which of the following enzymes is not used in the diagnosis of
    myocardial infarction?"
6. Negative, as described in Part 1."""

MCQ_RULES_ENGLISH = """Write LANGUAGE questions only. No medicine, no biology, no anatomy.
1. Grammar transformation, where the options are four full sentences:
   "I respect my teacher."
   "Rustam said, 'I want peace'."
   "He did not drive a car. The affirmative sentence of this is"
2. Direct and indirect narration:
   "I said to him, 'who are you'?"
   "The boy said to the girl, 'I can hear you'. The indirect narration is"
3. Identify the phrase or clause in quoted words:
   "The students look 'at the beautiful baby'. The quoted words are"
   Options: Adjective phrase, Noun clause, Adjective clause,
   Prepositional phrase.
4. Report, letter and memo terminology:
   "Appendix is placed at the ......... of report."
   "A memo should be ended on the note of ........."
   "Letter that is sent to family, friend and relative is called ........."
   "In full block letter everything must be to the extreme ......... of page."
5. Counting:
   "In report writing there are ......... parts."
   "There are ......... kinds of clauses?"
   "Writing styles can be divided into ......... different kinds."
6. Word meaning and word form:
   "The noun of poor is ........."
   "Comprehension means ........."
7. Essay, listening and presentation:
   "In which type of essay the writer describes a place, an object and an event"
   "The important component of hearing is ....?"
8. Negative, as described in Part 1."""

MCQ_RULES_OUTPUT = """RULES FOR THE OUTPUT:
- Exactly 4 options each. Exactly ONE is correct.
- Write only the option text, without A/B/C/D labels; the interface adds labels.
- Wrong options must be plausible, not obviously silly.
- Base every question AND the correct answer ONLY on the context given.
  Do not use outside knowledge. Do not invent facts.
- For numbers/classifications, state exactly what is being counted. Distinguish
  original components from fused/named groups and nerves from ganglia. Omit a
  numerical question if the supplied context leaves the counting level unclear.
- Put that counting level in the question itself, not just its explanation.
  For example, specify "original segmental ganglia before fusion" versus
  "named groups after fusion". Never ask a bare ganglion count.
- Options must differ in meaning. Reordering the same list of structures does
  not make different answers unless the stem explicitly asks for their order.
- Never use a synonym of the correct answer as a distractor. For example,
  anterior and ventral spinal roots name the same root, as do posterior and
  dorsal roots. Check that only one option answers the exact stem.
- Every question must test a DIFFERENT fact or idea. No two questions may
  ask about the same fact, even in different words.
- Add a short explanation and the page number for the correct answer."""

MCQ_RULES_BY_SUBJECT = {
    "Anatomy": MCQ_RULES_SCIENCE,
    "Physiology": MCQ_RULES_SCIENCE,
    "Biochemistry": MCQ_RULES_BIOCHEM,
    "English": MCQ_RULES_ENGLISH,
}


def generate_mcq_batch(topic, subject, book_name, context, n, avoid_questions, groq_client):
    st.session_state.pop('mcq_last_error', None)
    st.session_state.pop('mcq_last_error_kind', None)
    avoid_txt = ""
    if avoid_questions:
        joined = "\n".join(f"- {q}" for q in avoid_questions[-40:])
        avoid_txt = ("\nALREADY USED — do not repeat these, and do not ask the same "
                     "fact in different words:\n" + joined + "\n")

    subject_rules = MCQ_RULES_BY_SUBJECT.get(subject, "")
    subject_part = ""
    if subject_rules:
        subject_part = (f"\nPART 2 - HOW {subject.upper()} QUESTIONS ARE WRITTEN\n"
                        + subject_rules + "\n")

    prompt = f"""You are writing a Khyber Medical University MCQ paper for
BS Paramedics, 2nd Semester.

THE SUBJECT IS: {subject}
THE ONLY SOURCE IS: {book_name}

Write {n} multiple-choice questions on the topic: "{topic}".

Every question, every option, and every correct answer must come from the
{subject} text printed at the bottom of this message. Do not use your own
knowledge. Do not bring in any other subject. If the text does not cover
something, do not ask about it.

PART 1 - RULES FOR EVERY SUBJECT
{MCQ_RULES_GENERAL}
{subject_part}
{MCQ_RULES_OUTPUT}
- Keep each explanation to ONE short sentence (at most 20 words).
- The page reference must name "{book_name}" and a page number taken from
  the context headings, never a page you guessed.
{avoid_txt}
Return ONLY valid JSON, no other text. Use this exact format:
[
  {{
    "question": "....",
    "options": ["First option text", "Second option text", "Third option text", "Fourth option text"],
    "answer_index": 0,
    "explanation": "....",
    "page": "{book_name}, page X"
  }}
]

{subject} CONTEXT:
{context}

JSON:"""

    last_error = ""
    error_kind = "validation"
    for attempt in range(1):
        try:
            raw, provider = call_llm(prompt, groq_client, max_tokens=min(6000, n * 300 + 200),
                                     temperature=0.5, model=GROQ_MCQ_MODEL,
                                     validator=lambda text: len(parse_mcqs(text, book_name, context)) >= max(1, n // 2))
            st.session_state["last_provider"] = provider
            clean = parse_mcqs(raw, book_name, context)

            if clean:
                return clean
            last_error = "model returned no usable questions"

        except Exception as e:
            last_error = str(e)
            error_kind = "provider"
            # The provider chain already tried the available services.
            break

    if last_error:
        st.session_state["mcq_last_error"] = last_error
        st.session_state["mcq_last_error_kind"] = error_kind
    return []


def generate_all_mcqs(topic, subject, selected_book, model, collection, groq_client, progress,
                      focus_topics=(), existing_mcqs=()):
    started = time.perf_counter()
    st.session_state.pop("mcq_last_error", None)
    st.session_state.pop("mcq_last_error_kind", None)
    st.session_state.pop("mcq_request_deadline", None)
    st.session_state["mcq_timing"] = {"batches": 0}
    cache_key = (topic.strip().casefold(), subject, selected_book, MCQ_TOTAL)
    cache = st.session_state.setdefault("quiz_cache", {})
    cached = cache.get(cache_key) if not existing_mcqs else None
    if cached and time.monotonic() - cached[0] < 3600:
        if any(q.get("_option_order_version") != 2 for q in cached[1]):
            cached = (cached[0], balance_mcq_options(cached[1]), cached[2])
            cache[cache_key] = cached
        st.session_state["last_provider"] = cached[2]
        st.session_state["mcq_timing"].update(search_seconds=0, total_seconds=0, cached=True)
        progress.progress(1.0, text="Saved questions ready.")
        return cached[1]
    chunks, metas = retrieve(topic, selected_book, model, collection, MCQ_CONTEXT_K, focus_topics)
    st.session_state["mcq_timing"]["search_seconds"] = time.perf_counter() - started
    if not chunks:
        return list(existing_mcqs[:MCQ_TOTAL])
    # ---- words we ignore when comparing two questions ----
    STOP = {"the", "of", "a", "an", "is", "are", "was", "were", "what", "which",
            "following", "in", "to", "and", "for", "from", "that", "this", "how",
            "many", "all", "does", "do", "with", "its", "about", "within", "one",
            "or", "by", "be", "as", "at", "on", "it", "their", "these", "those",
            "there", "than", "then", "most", "also", "known", "called",
            "acid", "acids"}

    def stem(w):
        """Cut common endings so 'enzyme' and 'enzymes', 'hydrolysed' and
        'hydrolyses' count as the same word."""
        for suf in ("ation", "izes", "ises", "ing", "ied", "ies", "ed", "es", "s"):
            if len(w) > len(suf) + 3 and w.endswith(suf):
                return w[:-len(suf)]
        return w

    def words_of(text):
        """The meaningful words of a piece of text, for comparing two of them."""
        text = re.sub(r"^[A-D][.)\s]+", "", str(text))
        return {stem(w) for w in re.findall(r"[a-z0-9]+", text.lower())
                if w not in STOP and (len(w) > 2 or w.isdigit())}

    def overlap(a, b):
        """0 means nothing in common, 1 means exactly the same words."""
        both = a | b
        return len(a & b) / len(both) if both else 0.0

    def fingerprint(q):
        """Three word-sets: the question, all the options, the correct option."""
        opts = [str(o) for o in (q.get("options") or [])]
        try:
            ans = opts[q["answer_index"]]
        except Exception:
            ans = ""
        return (words_of(q.get("question", "")),
                words_of(" ".join(opts)),
                words_of(ans))

    def is_repeat(fp, kept, answer_counts, strict):
        """True if this question asks something we already have.

        Three signs of a repeat, any one is enough:
          - the wording is nearly the same
          - the correct answer is the same AND the subject is the same
          - the wording is close AND the options are mostly the same
        The strict rules run first. If the book simply has no more material,
        the loop below loosens them so the student still gets a full paper.
        """
        qw, ow, aw = fp
        if len(qw) < 2:
            return True                      # empty or broken question
        for pqw, pow_, paw in kept:
            qsame = overlap(qw, pqw)
            if qsame > (0.65 if strict else 0.80):
                return True
            if not strict:
                continue
            if overlap(aw, paw) > 0.6 and qsame > 0.25:
                return True
            if qsame > 0.45 and overlap(ow, pow_) > 0.5:
                return True
        if strict and aw and answer_counts.get(" ".join(sorted(aw)), 0) >= 2:
            return True                      # same answer already right twice
        return False

    all_mcqs = list(existing_mcqs[:MCQ_TOTAL])
    avoid = [q['question'] for q in all_mcqs]
    kept = [fingerprint(q) for q in all_mcqs]
    answer_counts = {}
    for _, _, answer_words in kept:
        answer_key = ' '.join(sorted(answer_words))
        if answer_key:
            answer_counts[answer_key] = answer_counts.get(answer_key, 0) + 1
    strict = True
    empty_rounds = 0

    # Bound the work even when only one new question survives each batch.
    rounds = 0
    st.session_state["mcq_request_deadline"] = time.monotonic() + 150
    while len(all_mcqs) < MCQ_TOTAL and rounds < 10:
        if time.monotonic() >= st.session_state["mcq_request_deadline"]:
            st.session_state["mcq_last_error"] = "The generation time budget was reached. You can continue this set."
            break
        rounds += 1
        if empty_rounds >= 3:
            if strict:
                # nothing new is getting through; loosen the filter rather
                # than hand back fewer questions than asked for
                strict = False
                empty_rounds = 0
            else:
                break

        need = min(MCQ_BATCH, MCQ_TOTAL - len(all_mcqs))
        # Retrieve a wide pool once, then cover different parts in each batch.
        # Sending all 45 chunks every time wastes tokens and hits free quotas.
        window_size = 15
        window_count = (len(chunks) + window_size - 1) // window_size
        offset = ((rounds - 1) % window_count) * window_size
        batch_context = compact_context(chunks[offset:offset + window_size],
                                        metas[offset:offset + window_size])
        # ask for extras, since repeats get thrown away
        progress.progress(len(all_mcqs) / MCQ_TOTAL,
                          text=f"Made {len(all_mcqs)} of {MCQ_TOTAL} questions. Generating batch {rounds}...")
        st.session_state["mcq_timing"]["batches"] = rounds
        batch = generate_mcq_batch(topic, subject, selected_book, batch_context,
                                   need + 2, avoid, groq_client)
        if (not batch and st.session_state.get("mcq_last_error")
                and st.session_state.get("mcq_last_error_kind", "provider") == "provider"):
            break

        added = 0
        for q in batch:
            fp = fingerprint(q)
            if is_repeat(fp, kept, answer_counts, strict):
                continue
            kept.append(fp)
            akey = " ".join(sorted(fp[2]))
            if akey:
                answer_counts[akey] = answer_counts.get(akey, 0) + 1
            all_mcqs.append(q)
            avoid.append(q["question"])
            added += 1
            if len(all_mcqs) >= MCQ_TOTAL:
                break

        empty_rounds = 0 if added else empty_rounds + 1

        progress.progress(min(len(all_mcqs) / MCQ_TOTAL, 1.0),
                          text=f"Made {len(all_mcqs)} of {MCQ_TOTAL} questions...")

    st.session_state["mcq_timing"]["total_seconds"] = time.perf_counter() - started
    st.session_state.pop("mcq_request_deadline", None)
    prefix_count = min(len(existing_mcqs), MCQ_TOTAL)
    all_mcqs = (all_mcqs[:prefix_count]
                + balance_mcq_options(all_mcqs[prefix_count:], all_mcqs[:prefix_count]))
    if len(all_mcqs) >= MCQ_TOTAL:
        if len(cache) >= 6:
            del cache[next(iter(cache))]
        cache[cache_key] = (time.monotonic(), all_mcqs[:MCQ_TOTAL],
                            st.session_state.get("last_provider", ""))
    return all_mcqs[:MCQ_TOTAL]


def _use_topic_suggestion(topic_queries):
    selected = st.session_state.get("topic_suggestion")
    if selected in topic_queries:
        st.session_state["query_text"] = topic_queries[selected]


def _custom_topic_changed():
    # A suggestion supplies the spelling; the editable question controls scope.
    st.session_state["topic_suggestion"] = None


def _upgrade_mcq_option_order():
    """Repair saved sets once while preserving the meaning of chosen answers."""
    old_questions = st.session_state.get("mcqs", [])
    if not old_questions or all(q.get("_option_order_version") == 2 for q in old_questions):
        return
    reordered = balance_mcq_options(old_questions)
    saved_answers = st.session_state.get("_mcq_answer_state", {}).get("answers", {})
    for index, (old, new) in enumerate(zip(old_questions, reordered)):
        mapping = {old["options"][origin]: new["options"][position]
                   for position, origin in enumerate(new["_option_origin_indices"])}
        key = f"ans_{index}"
        if key in st.session_state:
            st.session_state[key] = mapping.get(st.session_state[key])
        if index in saved_answers:
            choice = mapping.get(saved_answers[index])
            if choice is not None:
                saved_answers[index] = choice
            else:
                saved_answers.pop(index)
    st.session_state["mcqs"] = reordered


# ==================== UI ====================
st.set_page_config(page_title="AHS Study Assistant", page_icon="🎀",
                   layout="wide", initial_sidebar_state="expanded")
st.markdown(SANRIO_CSS, unsafe_allow_html=True)

# Theme toggle state
if "dark" not in st.session_state:
    st.session_state["dark"] = False


if not (GROQ_KEYS or CEREBRAS_API_KEY or GEMINI_API_KEY):
    st.error("No API key found. Add GROQ_API_KEY, CEREBRAS_API_KEY or "
             "GEMINI_API_KEY in .streamlit/secrets.toml")
    st.stop()

# Load the search resources on demand, then reuse Streamlit's resource cache.
model, collection, groq_client = None, None, None
_upgrade_mcq_option_order()

# ---------------- SIMPLE STUDY CONTROLS ----------------
if "sel_subject" not in st.session_state:
    st.session_state["sel_subject"] = st.session_state.get("saved_subject", "Physiology")

active_sources = SOURCES[st.session_state["sel_subject"]]
active_source = st.session_state.get("sel_source", st.session_state.get("saved_source"))
if active_source not in active_sources:
    active_source = next(iter(active_sources))
active_book = active_sources[active_source]
saved_study = st.session_state.get("study_result")
has_results = bool((st.session_state.get("mcqs") and st.session_state.get("quiz_book") == active_book)
                   or (saved_study and saved_study[0] == active_book))
layout_marker = "results-layout" if has_results else "landing-layout"
st.markdown(f'<div class="{layout_marker}"></div>', unsafe_allow_html=True)
heading_col, theme_control = st.columns([5, 1], gap="small")
with heading_col:
    st.markdown('<div class="hero"><div class="hero-eyebrow">BS Allied Health Sciences &middot; Semester 2</div>'
                '<div class="hero-title">2nd Semester Study Assistant</div></div>', unsafe_allow_html=True)
with theme_control:
    dark_on = st.toggle("Dark mode", value=st.session_state.get("dark", False), key="dark_toggle")
    if dark_on != st.session_state.get("dark", False):
        st.session_state["dark"] = dark_on
        st.rerun()
if st.session_state.get("dark", False):
    st.markdown(DARK_CSS, unsafe_allow_html=True)

with st.container(border=True):
    subject_col, source_col = st.columns([2, 1], gap="medium")
    with subject_col:
        subject = st.selectbox("Subject", list(SOURCES.keys()), key="sel_subject")
    with source_col:
        source_options = list(SOURCES[subject].keys())
        if st.session_state.get("sel_source") not in source_options:
            saved_source = st.session_state.get("saved_source")
            st.session_state["sel_source"] = saved_source if saved_source in source_options else source_options[0]
        source_type = st.radio("Study from", source_options, key="sel_source", horizontal=True)
    st.session_state["saved_subject"] = subject
    st.session_state["saved_source"] = source_type

book_choice = SOURCES[subject][source_type]


with st.container():
    with st.container(key="setup_controls"):
        if st.session_state.get("query_subject", subject) != subject:
            st.session_state["query_text"] = ""
            st.session_state["topic_suggestion"] = None
        st.session_state["query_subject"] = subject
        topic_queries = dict(get_topic_suggestions(subject))
        if st.session_state.get("topic_suggestion") not in topic_queries:
            st.session_state["topic_suggestion"] = None
        st.selectbox("Find a syllabus topic", tuple(topic_queries), index=None,
                     key="topic_suggestion", placeholder="Type a few letters, e.g. ner",
                     filter_mode="fuzzy", on_change=_use_topic_suggestion, args=(topic_queries,),
                     help="Search topics and subtopics for this subject. Select one to fill the question below.")
        query = st.text_input("Your question or topic", key="query_text",
                              placeholder="Choose a topic above or type your own question",
                              on_change=_custom_topic_changed)
        fresh_mcqs = st.checkbox("Make fresh questions", key="fresh_mcqs",
                                 help="Generate another set instead of reusing saved MCQs for this topic.")
        request = query
        focus_topics = ()

    b1, b2 = st.columns(2, gap="medium")
    with b1:
        study_clicked = st.button("Topic Study", key="btn_study",
                                  width="stretch", type="secondary")
    with b2:
        mcq_clicked = st.button("Generate 40 MCQs", key="btn_mcq",
                                width="stretch", type="primary")

    if study_clicked:
        st.session_state["workspace_view"] = "Study notes"
    elif mcq_clicked:
        st.session_state["workspace_view"] = "MCQs"
    workspace_view = st.session_state.get("workspace_view", "Study notes")
    if workspace_view == "Practice quiz":
        workspace_view = "MCQs"
        st.session_state["workspace_view"] = workspace_view
    if (study_clicked or mcq_clicked) and not query.strip():
        st.info("Type a topic or question first.")

    # Keep the answer on screen across theme changes and MCQ interactions.
    if study_clicked and query.strip():
        st.session_state.pop("study_result", None)
        with st.spinner("Reading your books..."):
            try:
                model, collection = load_model(), load_collection()
                answer, diagram_pages = answer_question(
                    request, subject, book_choice, model, collection, groq_client, focus_topics)
                st.session_state["study_result"] = (book_choice, query, answer,
                    diagram_pages, st.session_state.get("last_provider", ""))
                st.rerun()
            except Exception as error:
                st.error(friendly_error(error))
    result = st.session_state.get("study_result")
    if result and result[0] == book_choice and workspace_view == "Study notes":
        _, answered_topic, answer, diagram_pages, provider = result
        st.markdown("### Study notes")
        st.caption(f"Topic: {answered_topic}")
        st.markdown(answer)
        st.caption(f"Answered using: {provider}")
        if diagram_pages:
            with st.expander("Diagrams from your source"):
                # Expander contents execute even while collapsed; gate PDF work.
                page_choice = st.selectbox("Source page", diagram_pages,
                    format_func=lambda item: f"{item[0]} - PDF page {item[1]}",
                    key="source_page_choice")
                if st.button("Load selected page", key="load_source_page"):
                    st.session_state["loaded_source_page"] = (book_choice, answered_topic, page_choice)
                if st.session_state.get("loaded_source_page") == (book_choice, answered_topic, page_choice):
                    bk, pg = page_choice
                    try:
                        st.image(render_page(bk, pg), caption=f"{bk} - PDF page {pg}",
                                 width="stretch")
                    except Exception:
                        st.caption(f"Could not show page {pg}.")


    # ---- Generate MCQs ----
    if mcq_clicked and query.strip():
        topic = request
        if fresh_mcqs:
            st.session_state.get("quiz_cache", {}).pop(
                (topic.strip().casefold(), subject, book_choice, MCQ_TOTAL), None)
        quiz_started = time.perf_counter()
        progress = st.progress(0.0, text="Starting...")
        try:
            saved = st.session_state.get("quiz_cache", {}).get(
                (topic.strip().casefold(), subject, book_choice, MCQ_TOTAL))
            if saved and time.monotonic() - saved[0] < 3600:
                model, collection = None, None
            else:
                model, collection = load_model(), load_collection()
            mcqs = generate_all_mcqs(topic, subject, book_choice, model,
                                         collection, groq_client, progress, focus_topics)
        except Exception as error:
            st.error(friendly_error(error))
            mcqs = []
        progress.empty()
        if not mcqs:
            reason = st.session_state.get("mcq_last_error", "")
            if "rate" in reason.lower() or "429" in reason:
                st.warning("Groq's free limit is hit right now. Wait a minute and press Generate again.")
            elif reason:
                st.warning("Could not make valid questions. Try again or choose a broader topic.")
            else:
                st.warning("Could not make questions — this topic may be too thin in the selected source. Try a broader topic, or switch Book/Slides.")
        else:
            # A new question set starts without the previous choices.
            for _old in [k for k in list(st.session_state.keys())
                         if k.startswith("ans_")]:
                del st.session_state[_old]
            st.session_state["mcqs"] = mcqs
            st.session_state["quiz_book"] = book_choice
            st.session_state["quiz_topic"] = query
            st.session_state["quiz_request"] = topic
            st.session_state["quiz_focus"] = focus_topics
            st.session_state["quiz_id"] = st.session_state.get("quiz_id", 0) + 1
            if len(mcqs) < MCQ_TOTAL:
                st.warning(f"{len(mcqs)} of 40 questions ready. Some questions were repeated, invalid, "
                           "or the provider stopped. You can generate the remaining questions below.")
            st.success(f"{len(mcqs)} questions ready — answer them below.")
        if mcqs:
            st.session_state["quiz_ready_seconds"] = time.perf_counter() - quiz_started
            st.rerun()

    if workspace_view == "MCQs":
        if st.session_state.get("mcqs") and st.session_state.get("quiz_book") == book_choice:
            current_mcqs = st.session_state["mcqs"]
            st.caption(f"{len(current_mcqs)} / 40 questions ready · "
                       f"Prepared in {st.session_state.get('quiz_ready_seconds', 0):.1f}s"
                       + (f" · {st.session_state.get('last_provider')}" if st.session_state.get('last_provider') else ""))
            if len(current_mcqs) < MCQ_TOTAL:
                st.info(f"{len(current_mcqs)} / {MCQ_TOTAL} MCQs available. "
                        "A narrow topic may not support 40 different questions from this source.")
                if st.button("Complete remaining questions", key="complete_mcqs", type="primary"):
                    progress = st.progress(len(current_mcqs) / MCQ_TOTAL,
                                           text="Keeping your questions and making the rest...")
                    try:
                        model, collection = load_model(), load_collection()
                        completed = generate_all_mcqs(st.session_state["quiz_request"], subject,
                            book_choice, model, collection, groq_client, progress,
                            st.session_state.get("quiz_focus", ()), current_mcqs)
                        st.session_state["mcqs"] = completed
                        if len(completed) > len(current_mcqs):
                            st.rerun()
                        else:
                            st.warning("No new valid questions were added. Try again when the provider "
                                       "is available, or choose a broader topic.")
                    except Exception as error:
                        st.error(friendly_error(error))
                    progress.empty()
            render_mcqs(st.session_state["mcqs"], st.session_state.get("quiz_id", 0),
                        st.session_state.get("quiz_topic", ""))
        elif has_results:
            st.caption("Type a topic above and generate MCQs to start.")
    elif has_results and (not result or result[0] != book_choice):
        st.caption("Choose a topic above and open Topic Study to see your notes.")


# ---------------- FOOTER ----------------
st.markdown(
    """
    <div class="foot">
      <div>
        <div class="foot-name">Created by Abbas Khan</div>
        <div class="foot-role">BS Allied Health Sciences &middot; 2nd Semester</div>
      </div>
      <div class="foot-links">
        <a href="tel:+923459059934">
          <img src="https://cdn.jsdelivr.net/gh/simple-icons/simple-icons/icons/whatsapp.svg">0345-9059934</a>
        <a href="mailto:abbaskhan98491@gmail.com">
          <img src="https://cdn.jsdelivr.net/gh/simple-icons/simple-icons/icons/gmail.svg">Email</a>
        <a href="https://www.tiktok.com/@abbas_khan455" target="_blank">
          <img src="https://cdn.jsdelivr.net/gh/simple-icons/simple-icons/icons/tiktok.svg">TikTok</a>
        <a href="https://www.instagram.com/dentistabbaskhan" target="_blank">
          <img src="https://cdn.jsdelivr.net/gh/simple-icons/simple-icons/icons/instagram.svg">Instagram</a>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)
