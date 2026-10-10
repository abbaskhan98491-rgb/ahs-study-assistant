"""Regression checks for relevant figures using PDF-page API fixtures.

The fixtures do not author PDFs or require an AI provider. They model the same
text boxes, image placement and vector paths inspected in the actual sources.
"""

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from diagram_utils import select_diagram_pages


def text_block(text, box=(80, 50, 500, 85)):
    return (*box, text, 0, 0)


def image(box=(100, 120, 450, 350), width=700, height=460):
    return {"bbox": box, "width": width, "height": height}


class Page:
    rect = (0, 0, 600, 800)

    def __init__(self, blocks, images=(), drawings=()):
        self.blocks = blocks
        self.images = list(images)
        self.drawings = list(drawings)

    def get_text(self, mode):
        assert mode == "blocks"
        return self.blocks

    def get_image_info(self):
        return self.images

    def get_drawings(self):
        return self.drawings


class Document:
    def __init__(self, pages):
        self.pages = pages
        self.read_pages = []

    def __len__(self):
        return len(self.pages)

    def __getitem__(self, index):
        self.read_pages.append(index)
        return self.pages[index]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def figure_page(topic="Nephron"):
    return Page([text_block("Kidney physiology"),
                 text_block(f"FIGURE 3.1: {topic}", (100, 360, 470, 385))], [image()])


class DiagramSelectionTests(unittest.TestCase):
    def select(self, pages, question="nephron", book="Book.pdf", metas=None, chunks=None, limit=3):
        document = Document(pages)
        open_pdf = Mock(return_value=document)
        module = SimpleNamespace(open=open_pdf)
        metas = metas if metas is not None else [
            {"book": book, "page": number + 1, "has_diagram": True}
            for number in range(len(pages))]
        chunks = chunks if chunks is not None else [question] * len(metas)
        with patch.dict(sys.modules, {"pymupdf": module}):
            result = select_diagram_pages(question, chunks, metas, book, book, limit)
        return result, document, open_pdf

    def test_requires_topic_in_nearby_caption_not_merely_body_text(self):
        wrong = Page([text_block("Nephron structure"),
                      text_block("FIGURE 1.2: Heart valves", (100, 360, 480, 390)),
                      text_block("The nephron filters blood.", (80, 450, 510, 480))], [image()])
        result, _, _ = self.select([wrong, figure_page()])
        self.assertEqual(result, [("Book.pdf", 2)])

    def test_caption_must_be_physically_near_figure(self):
        page = Page([text_block("FIGURE 1.1: Nephron", (80, 650, 480, 675))], [image()])
        self.assertEqual(self.select([page])[0], [])

    def test_caption_can_use_space_instead_of_colon_after_figure_number(self):
        page = Page([text_block("FIGURE 9.64 Various stages of nephron development",
                                (100, 360, 470, 385))], [image()])
        self.assertEqual(self.select([page])[0], [("Book.pdf", 1)])

    def test_running_body_references_are_not_figure_captions(self):
        for content in ("As shown in FIGURE 9.64, the nephron filters blood.",
                        "FIGURE 9.64 shows how the nephron filters blood."):
            with self.subTest(content=content):
                page = Page([text_block(content, (100, 360, 470, 385))], [image()])
                self.assertEqual(self.select([page])[0], [])

    def test_text_only_and_tiny_logo_slides_are_not_diagrams(self):
        blocks = [text_block("Nephron structure")]
        pages = [Page(blocks), Page(blocks, [image((545, 20, 570, 45), 250, 250)])]
        self.assertEqual(self.select(pages, book="Lecture-Slides.pdf")[0], [])

    def test_relevant_large_slide_figure_with_heading_is_allowed(self):
        page = Page([text_block("Structure of Nephrons")], [image()])
        self.assertEqual(self.select([page], book="Lecture-Slides.pdf")[0],
                         [("Lecture-Slides.pdf", 1)])

    def test_body_mention_under_unrelated_slide_heading_is_rejected(self):
        page = Page([text_block("The heart"),
                     text_block("Nephron is discussed elsewhere", (80, 420, 520, 470))], [image()])
        self.assertEqual(self.select([page], book="Lecture-Slides.pdf")[0], [])

    def test_specific_multiword_topic_must_match_caption(self):
        page = figure_page("Cardiac muscle")
        self.assertEqual(self.select([page], question="Compare cardiac and smooth muscle")[0], [])

    def test_metadata_image_flag_does_not_override_actual_pdf_evidence(self):
        metadata = [{"book": "Book.pdf", "page": 1, "has_diagram": False}]
        self.assertEqual(self.select([figure_page()], metas=metadata)[0], [("Book.pdf", 1)])

    def test_foreign_source_does_not_even_open_selected_pdf(self):
        metadata = [{"book": "Other.pdf", "page": 1, "has_diagram": True}]
        result, _, open_pdf = self.select([figure_page()], metas=metadata)
        self.assertEqual(result, [])
        open_pdf.assert_not_called()

    def test_selected_path_cannot_be_a_different_pdf(self):
        open_pdf = Mock()
        with patch.dict(sys.modules, {"pymupdf": SimpleNamespace(open=open_pdf)}):
            result = select_diagram_pages("nephron", ["nephron"],
                                          [{"book": "Book.pdf", "page": 1}],
                                          "Book.pdf", "Other.pdf")
        self.assertEqual(result, [])
        open_pdf.assert_not_called()

    def test_invalid_page_references_are_ignored(self):
        metadata = [{"book": "Book.pdf", "page": page}
                    for page in (-1, 0, True, 1.5, "invalid", 400, 1)]
        result, document, _ = self.select([figure_page()], metas=metadata)
        self.assertEqual(result, [("Book.pdf", 1)])
        self.assertEqual(document.read_pages, [0])

    def test_deduplicates_pages_and_honors_limit(self):
        metadata = [{"book": "Book.pdf", "page": n} for n in (2, 1, 2, 3)]
        result, document, open_pdf = self.select([figure_page()] * 3, metas=metadata, limit=2)
        self.assertEqual(result, [("Book.pdf", 2), ("Book.pdf", 1)])
        self.assertEqual(document.read_pages, [1, 0, 2])
        open_pdf.assert_called_once()

    def test_matching_caption_ranks_ahead_of_heading_only(self):
        heading = Page([text_block("Nephron structure")], [image()])
        result, _, _ = self.select([heading, figure_page()], book="Lecture-Slides.pdf", limit=1)
        self.assertEqual(result, [("Lecture-Slides.pdf", 2)])

    def test_contents_and_full_page_scans_are_rejected(self):
        contents = Page([text_block("Table of contents"),
                         text_block("FIGURE 1.1: Nephron", (100, 360, 470, 385))], [image()])
        scan = Page([text_block("Nephron structure")], [image((0, 0, 600, 800))])
        self.assertEqual(self.select([contents, scan], book="Lecture-Slides.pdf")[0], [])

    def test_groups_many_small_vector_paths_into_one_figure(self):
        drawings = []
        for row in range(5):
            for col in range(6):
                x, y = 100 + col * 30, 150 + row * 30
                drawings.append({"rect": (x, y, x + 25, y + 25), "items": [("c",), ("c",)]})
        page = Page([text_block("FIGURE 1.2: Nephron", (90, 305, 410, 330))], drawings=drawings)
        self.assertEqual(self.select([page])[0], [("Book.pdf", 1)])

    def test_background_rectangles_rules_and_vector_icons_are_rejected(self):
        drawings = [{"rect": (0, 0, 600, 800), "items": [("re",)]},
                    {"rect": (60, 50, 60, 150), "items": [("l",)]},
                    {"rect": (530, 20, 555, 45), "items": [("c",)] * 30}]
        page = Page([text_block("Nephron structure")], drawings=drawings)
        self.assertEqual(self.select([page], book="Lecture-Slides.pdf")[0], [])

    def test_missing_pdf_does_not_fail_text_answer(self):
        for error in (FileNotFoundError, PermissionError, RuntimeError):
            with self.subTest(error=error):
                with patch.dict(sys.modules, {"pymupdf": SimpleNamespace(open=Mock(side_effect=error))}):
                    self.assertEqual(select_diagram_pages(
                        "nephron", ["nephron"], [{"book": "Book.pdf", "page": 1}],
                        "Book.pdf", "Book.pdf"), [])

    def test_broken_page_does_not_hide_other_verified_pages(self):
        broken = Page([text_block("Nephron")])
        broken.get_image_info = Mock(side_effect=RuntimeError)
        self.assertEqual(self.select([broken, figure_page()])[0], [("Book.pdf", 2)])

    def test_bounds_inspection_to_twelve_retrieved_pages(self):
        _, document, _ = self.select([figure_page()] * 30)
        self.assertEqual(document.read_pages, list(range(12)))

    def test_weak_question_or_empty_candidates_performs_no_pdf_work(self):
        for question, metadata in [("Explain this", [{"book": "Book.pdf", "page": 1}]),
                                   ("Nephron", [])]:
            with self.subTest(question=question):
                result, _, open_pdf = self.select([], question=question, metas=metadata)
                self.assertEqual(result, [])
                open_pdf.assert_not_called()


if __name__ == "__main__":
    unittest.main()
