"""Real KMU past-paper MCQs, picked when they belong to the topic being studied.

past_papers.json holds questions typed from the student's own photos of past
papers. They are not an official answer key: each answer was set from the
standard textbook and checked a second time on its own; unreadable, flawed or
doubtful items were left out.

A past question is used only when it really belongs to the topic: the topic's
main words must be in the question (or its answer), and the correct answer must
be in the book text the app found for the topic. When in doubt, it is left out;
a wrong-topic question is worse than none.
"""

from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import re

# Common words that say nothing about the topic.
_STOP = frozenset("""
a about above after all also among an and any are as at be because been
before being below between both but by can cannot could did do does done
during each either except false following for from function functions has
have having how however if in incorrect into is it its least main mainly
may most much must name named no none not of on one only or other others
part parts primary role same should so some such than that the their them
then there these they this those through to true two type types under up
upon used very was were what when where which while who whom why will with
within would called known form forms found given into process level levels
""".split())


def _stem(word):
    for suffix in ("ation", "ions", "ion", "ies", "ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def words(text):
    """The meaningful words of a text, with endings trimmed."""
    return {_stem(w) for w in re.findall(r"[a-z0-9]+", str(text).casefold())
            if (len(w) > 3 or w.isdigit()) and w not in _STOP}


@lru_cache(maxsize=1)
def _bank():
    try:
        data = json.loads(Path(__file__).with_name("past_papers.json").read_text(encoding="utf-8"))
        rows = data.get("questions", [])
    except (OSError, ValueError, AttributeError):
        return ()                       # past papers are optional
    clean = []
    for row in rows:
        options = row.get("options")
        index = row.get("answer_index")
        if (isinstance(row.get("question"), str) and isinstance(options, list)
                and len(options) == 4 and all(isinstance(o, str) and o.strip() for o in options)
                and len({o.strip().casefold() for o in options}) == 4
                and type(index) is int and 0 <= index < 4):
            clean.append(row)
    return tuple(clean)


def _is_combining(option):
    return bool(re.match(r"\s*(?:all|none|both|either|neither)\b", option, re.I))


# Words that describe what to study about a topic, not the topic itself.
_SOFT = frozenset(words("""
structure structures metabolism classification regulation introduction overview
basic basics definition disorders disorder mechanism mechanisms synthesis
importance significance clinical features general physiology anatomy chemistry
biochemistry english composition properties steps pathway pathways
writing skills rules
"""))


def _same_word(a, b):
    """'glycolysis' and 'glycolytic' count as the same word; 'plexus' and
    'plexuses' too. Short words must match exactly."""
    if a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    # "nerv" (from nerves) and "nerve"; "phras" and "phrase"; but not
    # "cell" and "cellulose".
    if len(short) >= 4 and long_.startswith(short) and len(long_) - len(short) <= 3:
        return True
    return min(len(a), len(b)) >= 6 and a[:6] == b[:6]


def _has(word, bag):
    return any(_same_word(word, other) for other in bag)


def _topic_parts(topic):
    """'phrases and clauses' -> [{'phras'}, {'claus'}]; soft words dropped."""
    parts = []
    for piece in re.split(r"\band\b|\bor\b|[,&/;:]", str(topic), flags=re.I):
        found = words(piece)
        main = {w for w in found if w not in _SOFT} or found
        if main:
            parts.append(main)
    return parts


def score_question(row, context_words, topic_words):
    """How well one past question fits the topic (0 = not at all).

    Every main word of the topic must appear in the question or its correct
    answer ("brachial plexus" needs both words). A topic joined by "and"/"or"
    is several topics: "phrases and clauses" accepts a question on either. Being in the same book area
    is not enough: that let citric-acid-cycle questions into a urea-cycle
    quiz. Among the questions that pass, the ones whose words are most present
    in the book text found for the topic come first.
    """
    answer = row["options"][row["answer_index"]]
    answer_words = set() if _is_combining(answer) else words(answer)
    key = words(row["question"]) | answer_words
    # The paper's own title counts too: every question of the
    # "Carbohydrate Metabolism" class test belongs to that topic.
    titled = key | words(row.get("source", ""))
    if not any(all(_has(w, titled) for w in part) for part in topic_words):
        return 0.0
    return 0.01 + len(key & context_words) / max(len(key), 1)


def pick_past_questions(topic, subject, context, limit=8):
    """Up to `limit` past-paper MCQs for this subject that belong to the topic.

    `context` is the book text already retrieved for the topic. Returns copies
    shaped like generated MCQs, marked with past_paper=True.
    """
    if limit < 1 or not context:
        return []
    context_words = words(context)
    topic_words = _topic_parts(topic)
    if not topic_words:
        return []
    scored = []
    for row in _bank():
        if row.get("subject") != subject:
            continue
        score = score_question(row, context_words, topic_words)
        if score:
            scored.append((score, row))
    scored.sort(key=lambda item: -item[0])
    picked = []
    for _, row in scored[:limit]:
        source = row.get("source") or "KMU past paper"
        number = row.get("number")
        reference = f"{source}" + (f", Q{number}" if number else "")
        picked.append({
            "question": row["question"],
            "options": deepcopy(row["options"]),
            "answer_index": row["answer_index"],
            "explanation": "A real past-paper question. The answer was checked against the textbook.",
            "page": f"Past paper: {reference}",
            "past_paper": True,
            "past_source": reference,
        })
    return picked
