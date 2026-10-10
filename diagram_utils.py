"""Conservative, source-only figure selection after a study answer is ready.

Retrieval flags only say that a PDF page contains an image. They cannot tell
whether it is a relevant figure, a logo, or a scanned text page. Check the
actual few retrieved pages instead, and omit figures when evidence is weak.
"""

import math
import re
from dataclasses import dataclass
from pathlib import Path


_REQUEST_WORDS = frozenset("""
a an and are as at be by can could describe diagram diagrams do does explain
for from give how i in into is it me my of on or please show study tell that
the their these this to us was what when where which why with would you your
about briefly definition define introduction overview detail details detailed
structure structures function functions classification classify type types
simple words question topic book slide slides ke ki ka ko kya hai hy mein
samjhao batao bare
""".split())
_FIGURE_LABEL = re.compile(
    r"^\s*(?:fig(?:ure)?\.?)\s*\d+(?:\.\d+)*(?:[A-Z])?(?!\d|\.\d)"
    r"(?:\s*[:.\-]\s*|\s+)"
    r"(?!(?:shows?|illustrates?|depicts?|demonstrates?|presents?)\b)\S",
    re.IGNORECASE,
)
_DIAGRAM_LABEL = re.compile(r"^\s*(?:diagram|illustration)\s+(?:of|showing)\b", re.IGNORECASE)
_FRONT_MATTER = re.compile(
    r"\b(?:table of contents|contents|preface|acknowledg(?:e)?ments|"
    r"copyright|all rights reserved|bibliography|references|index)\b", re.IGNORECASE
)


@dataclass(frozen=True)
class _Region:
    box: tuple
    raster: bool
    grid: bool = False


def _tokens(text):
    words = re.findall(r"[a-z][a-z0-9]*", str(text).casefold())
    result = set()
    for word in words:
        if word in _REQUEST_WORDS or (len(word) < 3 and word not in {"na", "ca", "k"}):
            continue
        if len(word) > 4 and word.endswith("ies"):
            word = word[:-3] + "y"
        elif len(word) > 4 and word.endswith("s") and not word.endswith(("ss", "is", "us")):
            word = word[:-1]
        result.add(word)
    return result


def _match(topic, text):
    return len(topic & _tokens(text)) / len(topic) if topic else 0.0


def _box(value):
    try:
        result = tuple(float(x) for x in value)
        if len(result) != 4 or not all(math.isfinite(x) for x in result):
            return None
        return result if result[2] >= result[0] and result[3] >= result[1] else None
    except (TypeError, ValueError):
        return None


def _area(box):
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _intersection(a, b):
    return (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))


def _union(a, b):
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _near(a, b, padding):
    return (a[0] <= b[2] + padding and b[0] <= a[2] + padding
            and a[1] <= b[3] + padding and b[1] <= a[3] + padding)


def _large_enough(box, page_box, fraction=.035):
    width, height = page_box[2] - page_box[0], page_box[3] - page_box[1]
    return (_area(box) >= _area(page_box) * fraction
            and box[2] - box[0] >= width * .14
            and box[3] - box[1] >= height * .08)


def _figure_regions(page, page_box):
    regions = []
    for image in page.get_image_info():
        box = _box(image.get("bbox"))
        if box is None or image.get("width", 0) < 64 or image.get("height", 0) < 48:
            continue
        box = _intersection(box, page_box)
        # Full-page scans and covers are not independently verified figures.
        if _large_enough(box, page_box) and _area(box) < _area(page_box) * .88:
            regions.append(_Region(box, True))

    # Related vector paths often form one diagram from many tiny components.
    # Merge nearby components; don't mistake page fills and separator rules for it.
    groups = []
    padding = min(page_box[2] - page_box[0], page_box[3] - page_box[1]) * .018
    for drawing in page.get_drawings()[:2000]:
        box = _box(drawing.get("rect"))
        items = drawing.get("items", [])
        if box is None or not items:
            continue
        box = _intersection(box, page_box)
        width, height = box[2] - box[0], box[3] - box[1]
        if width < 0 or height < 0 or _area(box) >= _area(page_box) * .7:
            continue
        kinds = [item[0] for item in items]
        # Rectangles alone are commonly slide backgrounds, table fills or borders.
        if all(kind == "re" for kind in kinds):
            continue
        if len(items) == 1 and (width < 1 or height < 1) and max(width, height) > padding * 6:
            continue
        group = {"box": box, "count": len(items), "curves": kinds.count("c"),
                 "h": int(height < 2), "v": int(width < 2)}
        merged = True
        while merged:
            merged = False
            for index, other in enumerate(groups):
                if _near(group["box"], other["box"], padding):
                    group["box"] = _union(group["box"], other["box"])
                    for key in ("count", "curves", "h", "v"):
                        group[key] += other[key]
                    groups.pop(index)
                    merged = True
                    break
        groups.append(group)
    for group in groups:
        if group["count"] >= 12 and _large_enough(group["box"], page_box):
            grid = group["curves"] == 0 and group["h"] >= 4 and group["v"] >= 4
            regions.append(_Region(group["box"], False, grid))
    return regions


def _caption_near(caption, region, page_box):
    a, b = caption, region.box
    overlap_x = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    gap_y = max(0, a[1] - b[3], b[1] - a[3])
    min_width = min(a[2] - a[0], b[2] - b[0])
    return (min_width > 0 and overlap_x >= min_width * .25
            and gap_y <= max(40, (page_box[3] - page_box[1]) * .08))


def _page_score(page, topic, is_slide):
    page_box = _box(page.rect)
    if page_box is None or _area(page_box) == 0:
        return 0
    blocks = []
    for block in page.get_text("blocks"):
        if len(block) >= 7 and block[6] == 0:
            box = _box(block[:4])
            text = str(block[4]).strip()
            if box is not None and text:
                blocks.append((box, text))
    if not blocks:
        return 0
    blocks.sort(key=lambda block: (block[0][1], block[0][0]))
    if any(_FRONT_MATTER.search(text) for _, text in blocks[:2]):
        return 0
    regions = _figure_regions(page, page_box)
    if not regions:
        return 0

    for box, text in blocks:
        if len(text.split()) > 85:
            continue
        if (_FIGURE_LABEL.search(text) or _DIAGRAM_LABEL.search(text)) and _match(topic, text) >= .75:
            if any(_caption_near(box, region, page_box) for region in regions):
                return 100

    if is_slide:
        # Caption-free lecture figures need both a topic heading and a substantial
        # visual. A matching word in ordinary body text is not enough evidence.
        height = page_box[3] - page_box[1]
        for box, text in blocks[:2]:
            if (box[1] < page_box[1] + height * .28 and len(text.split()) <= 18
                    and _match(topic, text) >= .75):
                if any(not region.grid and _large_enough(region.box, page_box, .12)
                       for region in regions):
                    return 80
    return 0


def select_diagram_pages(question, chunks, metas, selected_book, pdf_path, limit=3):
    """Return verified relevant figure pages, or [] when confidence is weak.

    Uses only the selected PDF and at most 12 distinct retrieved pages. It does
    not scan neighbors, generate pictures, trust metadata image flags, or fall
    back to unrelated pages. Missing files or extraction errors omit diagrams
    without preventing the student's text answer from loading.
    """
    topic = _tokens(question)
    try:
        limit = int(limit)
        selected_book = str(selected_book)
        if limit < 1 or not topic or Path(pdf_path).name.casefold() != selected_book.casefold():
            return []
    except (TypeError, ValueError):
        return []

    candidates = []
    for rank, (chunk, meta) in enumerate(zip(chunks, metas)):
        if not isinstance(meta, dict) or str(meta.get("book", "")).casefold() != selected_book.casefold():
            continue
        if not chunk or _match(topic, chunk) < .5:
            continue
        raw_page = meta.get("page")
        try:
            number = int(raw_page)
            if isinstance(raw_page, bool) or number < 1 or float(raw_page) != number:
                continue
        except (TypeError, ValueError, OverflowError):
            continue
        if number not in [item[0] for item in candidates]:
            candidates.append((number, rank))
        if len(candidates) >= 12:
            break
    if not candidates:
        return []

    try:
        import pymupdf

        verified = []
        with pymupdf.open(pdf_path) as document:
            for number, rank in candidates:
                if number > len(document):
                    continue
                try:
                    score = _page_score(document[number - 1], topic, "slide" in selected_book.casefold())
                except Exception:
                    # A malformed page must not discard an otherwise valid answer.
                    continue
                if score:
                    verified.append((score, rank, number))
        verified.sort(key=lambda item: (-item[0], item[1]))
        return [(selected_book, number) for _, _, number in verified[:limit]]
    except (ImportError, OSError, RuntimeError, ValueError, TypeError):
        return []
