"""Lightweight searchable topic choices from the existing local syllabus.

These are suggestions for the editable question, not textbook answers. Keep
source wording and do not load PDFs, search indexes or AI models for a picker.
"""

import json
from collections import defaultdict
from functools import lru_cache
from pathlib import Path


_SUBJECTS = {name.casefold(): name for name in
             ("Physiology", "Biochemistry", "Anatomy", "English")}
_GENERIC_TOPICS = frozenset({
    "definition", "introduction", "overview", "regulation", "chemical rationale",
    "atp calculation", "land marks", "landmarks",
})


def _clean(value):
    return " ".join(value.split()) if isinstance(value, str) else ""


def _identity(value):
    return _clean(value).casefold()


@lru_cache(maxsize=1)
def _load_subjects():
    """Read the small JSON once, only after a known subject needs suggestions."""
    try:
        data = json.loads(Path(__file__).with_name("syllabus_details.json").read_text(
            encoding="utf-8-sig"))
        subjects = data.get("subjects", {})
        return subjects if isinstance(subjects, dict) else {}
    except (OSError, UnicodeError, ValueError):
        # Suggestions are optional; the student's own question must still work.
        return {}


@lru_cache(maxsize=4)
def _catalogue(subject):
    units = _load_subjects().get(subject, {})
    if not isinstance(units, dict):
        return ()
    records = []
    contexts = defaultdict(set)
    for topics in units.values():
        if not isinstance(topics, dict):
            continue
        for raw_topic, rows in topics.items():
            topic = _clean(raw_topic)
            if not topic:
                continue
            outcomes = []
            seen_outcomes = set()
            for row in rows if isinstance(rows, list) else ():
                outcome = _clean(row.get("text", "")) if isinstance(row, dict) else ""
                identity = _identity(outcome)
                if outcome and identity not in seen_outcomes:
                    outcomes.append(outcome)
                    seen_outcomes.add(identity)
            records.append((topic, tuple(outcomes)))
            contexts[_identity(topic)].add(tuple(_identity(text) for text in outcomes))

    suggestions = []
    labels = set()

    def add(label, query):
        identity = _identity(label)
        if identity not in labels:
            labels.add(identity)
            suggestions.append((label, query))

    for topic, outcomes in records:
        topic_id = _identity(topic)
        ambiguous = topic_id in _GENERIC_TOPICS and len(contexts[topic_id]) > 1 and outcomes
        if not ambiguous:
            # Bare headings such as "Regulation" need their actual source context.
            query = outcomes[0] if topic_id in _GENERIC_TOPICS and outcomes else topic
            add(topic, query)
        for outcome in outcomes:
            if not ambiguous and _identity(outcome) == topic_id:
                continue
            add(f"{topic} · {outcome}", f"{topic}: {outcome}")
    return tuple(suggestions)


def get_topic_suggestions(subject):
    """Return immutable (display label, editable question) pairs for one subject.

    Unknown subjects and Islamic Studies return no options. Unit/chapter names
    are never exposed as a separate level. Case/whitespace duplicates disappear;
    outcomes keep their parent topic so short learning outcomes remain useful.
    """
    canonical = _SUBJECTS.get(_identity(subject))
    return _catalogue(canonical) if canonical else ()
