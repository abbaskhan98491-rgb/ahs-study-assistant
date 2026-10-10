"""Balance correct answer positions without changing option meanings."""

from copy import deepcopy
import random
import re


class _UnsafeReference(ValueError):
    pass


_ABOVE = re.compile(r"^(all|none)\s+(?:of\s+)?(?:the\s+)?above[.!]?$", re.I)
_COMBINING = re.compile(
    r"^(?:(both|either)\s+)?([A-D])\s*(and|or|&|\+)\s*([A-D])"
    r"(?:\s+only)?[.!]?$", re.I,
)
_EXPLICIT = re.compile(
    r"\b(?i:options?|answers?|choices?)\s*(?:(?i:is)|[:=])?\s*"
    r"\(?([A-D](?:\s*(?i:,|and|or|&|\+)\s*[A-D])*)\)?\b"
)
_CORRECT_REFERENCE = re.compile(
    r"\b([A-D])(?=\s+(?i:is|was)\s+(?:(?i:the)\s+)?(?i:correct|incorrect|right|wrong)\b)"
)
_CORRECT_COMBINATION = re.compile(
    r"\b([A-D](?:\s*(?i:,|and|or|&|\+)\s*[A-D])+)(?=\s+(?i:are|were)\s+"
    r"(?i:correct|incorrect|right|wrong|true|false)\b)"
)
_RELATIVE = re.compile(
    r"\b(?:all|none|both|either|neither)\b[^.;]*\b(?:above|below)\b|"
    r"\b(?:first|second|third|fourth|last|previous|preceding|following|above|below)\s+"
    r"(?:option|answer|choice)s?\b|\b(?:option|answer|choice)s?\s+(?:above|below)\b", re.I,
)
_LETTER_COMBINATION = re.compile(r"\b[A-D]\s*(?:,|and|or|&|\+)\s*[A-D]\b")
_BARE_REFERENCE = re.compile(r"\b[A-D]\s+(?:is|was|are|were|has|have|does|do|can|will)\b")
_PREFIX = re.compile(r"^\s*\(?([A-D])(?:\)|[.):\]-])\s+(.+)$")


def _quote(text):
    return f'“{text}”'


def _literal_letter(text, position):
    """These words identify a factual letter, rather than an option label."""
    before = text[:position]
    after = text[position + 1:]
    return bool(
        re.search(r"\b(?:vitamins?|blood\s+groups?|types?|classes?|grades?|groups?|forms?)\s*$", before, re.I)
        or re.match(r"\s*[- ]\s*(?:cells?|fibers?|waves?|bands?|DNA)\b", after, re.I)
    )


def _normalize_questions(question):
    options = list(question["options"])
    prefixes = [_PREFIX.fullmatch(option) for option in options]
    if all(prefixes) and [match[1] for match in prefixes] == list("ABCD"):
        options = [match[2] for match in prefixes]
    elif any(prefixes):
        raise _UnsafeReference("Inconsistent option labels cannot be safely reordered.")
    elif all(re.match(rf"^\s*{letter}\s+", option) for letter, option in zip("ABCD", options)):
        # Some providers emit "A Sodium" instead of "A. Sodium". A complete,
        # ordered set of labels can be removed, but factual letters such as
        # "A band" and "B cells" must retain their medical meaning.
        if any(_literal_letter(option, len(option) - len(option.lstrip())) for option in options):
            raise _UnsafeReference("Factual letter prefixes cannot be safely relabeled.")
        options = [re.sub(r"^\s*[A-D]\s+", "", option) for option in options]

    resolved = {}
    resolving = set()

    def resolve(index):
        if index in resolved:
            return resolved[index]
        if index in resolving:
            raise _UnsafeReference("Options contain cyclic or self-referencing answer letters.")
        resolving.add(index)
        resolved[index] = normalize(options[index], index)
        resolving.remove(index)
        return resolved[index]

    def letter_list(text):
        return re.sub(r"\b[A-D]\b", lambda match: _quote(resolve(ord(match[0]) - ord("A"))), text)

    def normalize(text, option_index=None):
        stripped = text.strip()
        above = _ABOVE.fullmatch(stripped)
        if above and option_index is not None:
            if option_index == 0:
                raise _UnsafeReference("An above-reference has no preceding options.")
            # Explicitly name the original preceding options. Simply changing
            # 'above' to 'these' would change a middle option's meaning.
            values = "; ".join(_quote(resolve(index)) for index in range(option_index))
            return f"{above[1].capitalize()} of these: {values}"
        combining = _COMBINING.fullmatch(stripped)
        if combining and option_index is not None:
            first = ord(combining[2].upper()) - ord("A")
            second = ord(combining[4].upper()) - ord("A")
            conjunction = "or" if combining[3].lower() == "or" else "and"
            leading = "Either " if conjunction == "or" else "Both "
            return f"{leading}{_quote(resolve(first))} {conjunction} {_quote(resolve(second))}"

        expansions = []

        def protect(value):
            expansions.append(value)
            return f"\x00{len(expansions) - 1}\x00"

        def explicit(match):
            return protect(letter_list(match[1]))

        def correct_reference(match):
            if _literal_letter(text, match.start()):
                return match[0]
            return protect(letter_list(match[1]))

        work = _EXPLICIT.sub(explicit, text)
        work = _CORRECT_COMBINATION.sub(correct_reference, work)
        work = _CORRECT_REFERENCE.sub(correct_reference, work)
        if _RELATIVE.search(work):
            raise _UnsafeReference("A position-relative option cannot be safely reordered.")
        if _LETTER_COMBINATION.search(work):
            raise _UnsafeReference("An ambiguous answer-letter combination cannot be safely expanded.")
        if any(not _literal_letter(work, match.start()) for match in _BARE_REFERENCE.finditer(work)):
            raise _UnsafeReference("An ambiguous answer-letter reference cannot be safely expanded.")
        # B/C/D used on their own can still be an unsupported option reference.
        # The letter A commonly serves as the article in a normal sentence.
        if any(not _literal_letter(work, match.start()) for match in re.finditer(r"\b[B-D]\b", work)):
            if option_index is None or work.strip() not in ("B", "C", "D"):
                raise _UnsafeReference("An unsupported answer-letter reference cannot be safely expanded.")
        return re.sub(r"\x00(\d+)\x00", lambda match: expansions[int(match[1])], work)

    normalized = [resolve(index) for index in range(4)]
    if len({option.strip().casefold() for option in normalized}) != 4:
        raise _UnsafeReference("Expanding references would create duplicate options.")
    result = deepcopy(question)
    result["options"] = normalized
    for field in ("question", "explanation"):
        if isinstance(result.get(field), str):
            result[field] = normalize(result[field])
    return result


def balance_mcq_options(mcqs, existing_mcqs=(), rng=None):
    """Return a balanced, randomly ordered copy of NEW questions only.

    Existing questions are used to count answer positions and remain untouched.
    Forty safe questions yield ten correct answers at each position. Correct
    targets are shuffled as a group so they do not follow a repeating cycle.
    Pass random.Random(seed) as rng for reproducible tests.

    Recognized option-letter references are expanded to the original option
    text. Unsafe questions retain their original order and receive an
    option_order_warning; their positions still count toward the balance.
    """
    rng = rng if rng is not None else random.Random()
    counts = [0, 0, 0, 0]
    for question in existing_mcqs:
        index = question.get("answer_index")
        if type(index) is int and 0 <= index < 4:
            counts[index] += 1

    prepared = []
    for question in mcqs:
        copied = deepcopy(question)
        try:
            if not (
                isinstance(copied.get("options"), list) and len(copied["options"]) == 4
                and all(isinstance(option, str) for option in copied["options"])
                and type(copied.get("answer_index")) is int and 0 <= copied["answer_index"] < 4
            ):
                raise _UnsafeReference("The option structure cannot be safely reordered.")
            copied = _normalize_questions(copied)
            copied.pop("option_order_warning", None)
            prepared.append((copied, True))
        except _UnsafeReference as error:
            copied["option_order_warning"] = str(error)
            prepared.append((copied, False))
            index = copied.get("answer_index")
            if type(index) is int and 0 <= index < 4:
                counts[index] += 1

    targets = []
    for _ in range(sum(safe for _, safe in prepared)):
        smallest = min(counts)
        target = rng.choice([index for index, count in enumerate(counts) if count == smallest])
        counts[target] += 1
        targets.append(target)
    rng.shuffle(targets)

    result = []
    for question, safe in prepared:
        order = list(range(4))
        if safe:
            target = targets.pop()
            correct = question["answer_index"]
            others = [index for index in range(4) if index != correct]
            rng.shuffle(others)
            order = []
            for index in range(4):
                order.append(correct if index == target else others.pop())
            question["options"] = [question["options"][index] for index in order]
            question["answer_index"] = target
        question["_option_origin_indices"] = order
        question["_option_order_version"] = 2
        result.append(question)
    return result
