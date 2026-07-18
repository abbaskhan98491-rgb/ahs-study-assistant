"""
Image Engine - renders exact pages from your PDF books as clear images.
This captures diagrams, reactions, tables, sketches - everything on the page,
exactly as printed in the book.

Setup (already installed): pip install pymupdf

Usage examples:
    python show_pages.py "Satyanarayana-biochemistry-pdf-free.pdf" 45 46 47
        -> renders pages 45, 46, 47 of that book into the page_images/ folder and opens them

    python show_pages.py list
        -> shows the exact names of your books so you can copy them
"""

import os
import sys
import fitz

BOOKS_DIR = "books"
OUT_DIR = "page_images"
ZOOM = 2  # 2 = clear + light. Raise to 3 for sharper (bigger files, slower).


def list_books():
    if not os.path.isdir(BOOKS_DIR):
        print(f"No '{BOOKS_DIR}' folder found.")
        return
    pdfs = [f for f in os.listdir(BOOKS_DIR) if f.lower().endswith(".pdf")]
    if not pdfs:
        print("No PDFs in books/ folder.")
        return
    print("Your books (copy the name exactly, with quotes):")
    for p in pdfs:
        print(f'   "{p}"')


def render_pages(book_name, page_numbers):
    path = os.path.join(BOOKS_DIR, book_name)
    if not os.path.isfile(path):
        print(f"ERROR: Can't find '{path}'.")
        print("Run:  python show_pages.py list   to see exact book names.")
        return

    os.makedirs(OUT_DIR, exist_ok=True)
    doc = fitz.open(path)
    total = len(doc)
    saved = []

    for pg in page_numbers:
        if pg < 1 or pg > total:
            print(f"  Skipped page {pg} (book has {total} pages).")
            continue
        page = doc[pg - 1]  # PDF pages are 0-indexed internally
        pix = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM))
        safe_book = "".join(c if c.isalnum() else "_" for c in book_name)[:30]
        out_path = os.path.join(OUT_DIR, f"{safe_book}_page_{pg}.png")
        pix.save(out_path)
        saved.append(out_path)
        print(f"  Saved: {out_path}")

    doc.close()

    # Try to auto-open the first image so you can see it
    if saved:
        print(f"\n{len(saved)} page image(s) saved in the '{OUT_DIR}' folder.")
        try:
            os.startfile(os.path.abspath(saved[0]))  # Windows only
        except Exception:
            print("Open the page_images folder yourself to view them.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
    elif sys.argv[1] == "list":
        list_books()
    else:
        book = sys.argv[1]
        try:
            pages = [int(x) for x in sys.argv[2:]]
        except ValueError:
            print("Page numbers must be numbers. Example:")
            print('   python show_pages.py "mybook.pdf" 45 46 47')
            sys.exit()
        if not pages:
            print("Give at least one page number.")
        else:
            render_pages(book, pages)
