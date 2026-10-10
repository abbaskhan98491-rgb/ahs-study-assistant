"""Small, dependency-free helpers for safe source context and quiz parsing."""
import json
import re


def friendly_error(error):
    """Report known local failures without exposing provider request details."""
    message = str(error).lower()
    if 'paging file' in message or '1455' in message:
        return 'Windows cannot load the search model: the paging file is too small. Free memory or increase Windows virtual memory, then restart the app.'
    if 'memory allocation' in message or isinstance(error, MemoryError):
        return 'Not enough memory to load the search model. Close other apps and restart this app.'
    return 'The request could not finish. Check provider availability and try again.'


def compact_context(chunks, metas):
    # Adjacent chunks overlap. Remove exact duplicate sentences without
    # dropping any retrieved page or inventing new textbook text.
    seen = set()
    sections = []
    for text, meta in zip(chunks, metas):
        sentences = re.split(r'(?<=[.!?])\s+', text)
        fresh = []
        for sentence in sentences:
            key = (meta['book'], meta['page'], sentence.strip())
            if key not in seen:
                fresh.append(sentence)
                seen.add(key)
        if fresh:
            sections.append(f"[{meta['book']}, page {meta['page']}]\n" + ' '.join(fresh))
    return '\n\n---\n\n'.join(sections)


def _equivalent_component_options(question, options):
    """Reject reordered member lists only when the stem asks for their contents."""
    if not re.search(r'\b(?:components|parts|layers|members|elements|constituents|'
                     r'structures|groups|divisions|categories|types|forms|'
                     r'include[sd]?|comprise[sd]?|consist[sd]?)\b', question, re.I):
        return False
    # Order and position make permutations legitimate, including English tasks.
    if re.search(r'\b(?:order(?:ed|ing)?|sequence|sequential|arrang(?:e|ed|ement)|'
                 r'first|second|third|last|before|after|preced(?:e|es|ing)|'
                 r'follow(?:ed|s|ing)|ascending|descending|increasing|decreasing|'
                 r'outer(?:most)?|inner(?:most)?|outside|inside|superficial|'
                 r'deep(?:est)?|front|back|left|right|beginning|end|top|bottom)\b',
                 question, re.I):
        return False
    fingerprints = []
    for option in options:
        # Strip an old option label without changing the returned option text.
        text = re.sub(r'^[A-D](?:[.)]\s*|\s+)', '', option.strip())
        components = text.split(',')
        if len(components) < 2 or any(not component.strip() for component in components):
            continue
        normalized = []
        for index, component in enumerate(components):
            component = component.strip().rstrip('.').strip()
            if index == len(components) - 1:
                component = re.sub(r'^and\s+', '', component, flags=re.I)
            normalized.append(re.sub(r'\s+', ' ', component).casefold())
        # Keep complete components intact: word order within each can change meaning.
        fingerprint = tuple(sorted(normalized))
        if fingerprint in fingerprints:
            return True
        fingerprints.append(fingerprint)
    return False


def _duplicate_spinal_root_options(question, options):
    """Do not present two names for the same spinal root as different answers."""
    # Anterior/ventral and posterior/dorsal are established root synonyms:
    # https://openstax.org/books/anatomy-and-physiology/pages/13-2-the-central-nervous-system
    # Keep this narrow: these adjectives are not equivalent in every structure.
    if not re.search(r'\b(?:spinal|nerve|preganglionic)\b', question, re.I):
        return False
    roots = set()
    for option in options:
        text = re.sub(r'^[A-D](?:[.)]\s*|\s+)', '', option.strip()).rstrip('.').strip()
        match = re.fullmatch(r'(anterior|ventral|posterior|dorsal)\s+'
                             r'(?:(?:spinal|nerve)\s+){0,2}roots?', text, re.I)
        if match:
            side = 'anterior' if match[1].lower() in ('anterior', 'ventral') else 'posterior'
            if side in roots:
                return True
            roots.add(side)
    return False


def _unclear_ganglion_count(question):
    """Require the counting level when a ganglion count can include fusion."""
    counts_ganglia = re.search(r'\b(?:how many|number of|count of)\s+'
                              r'(?:[\w-]+\s+){0,4}ganglia\b', question, re.I)
    scope = re.search(r'\b(?:original|segmental|unfused|fus(?:e|ed|ion)|'
                      r'groups?|named)\b', question, re.I)
    return bool(counts_ganglia and not scope)


def parse_mcqs(raw, book_name, context):
    """Recover complete JSON objects and reject malformed or wrong-source items."""
    decoder = json.JSONDecoder()
    items = []
    text = raw if isinstance(raw, str) else ''
    pos = 0
    while pos < len(text):
        start = text.find('{', pos)
        if start < 0:
            break
        try:
            item, end = decoder.raw_decode(text, start)
            pos = end
        except json.JSONDecodeError:
            pos = start + 1
            continue
        if not isinstance(item, dict):
            continue
        opts = item.get('options')
        if not (isinstance(opts, list) and len(opts) == 4
                and all(isinstance(o, str) and o.strip() for o in opts)
                and len({o.strip().casefold() for o in opts}) == 4
                and type(item.get('answer_index')) is int
                and 0 <= item['answer_index'] <= 3
                and isinstance(item.get('question'), str) and item['question'].strip()
                and isinstance(item.get('explanation'), str) and item['explanation'].strip()
                and isinstance(item.get('page'), str)):
            continue
        ref = re.fullmatch(re.escape(book_name) + r',\s*page\s+(\d+)', item['page'].strip())
        if not ref or f'[{book_name}, page {int(ref[1])}]' not in context:
            continue
        negative = re.search(r'\b(not|except|incorrect)\b', item['question'], re.I)
        combining = any(re.search(r'\b(all|none) of|\bboth [A-D] and [A-D]', o, re.I) for o in opts)
        if negative and combining:
            continue
        if _equivalent_component_options(item['question'], opts):
            continue
        if _duplicate_spinal_root_options(item['question'], opts):
            continue
        if _unclear_ganglion_count(item['question']):
            continue
        items.append(item)
    return items
