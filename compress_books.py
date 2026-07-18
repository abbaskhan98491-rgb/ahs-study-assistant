"""
Compress the PDFs in books/ so they can be uploaded online.

How it works:
  Each page is re-drawn as a compressed image. The text layer is dropped —
  that's fine, because the app already has all the text in rag_db.
  These compressed copies are ONLY used to show diagrams.

Output goes to:  books_small/
Your original books/ folder is NOT touched.

Usage:
    python compress_books.py            -> normal (DPI 90, quality 55)
    python compress_books.py 70 45      -> smaller files, lower quality
    python compress_books.py 120 70     -> bigger files, sharper
"""

import os
import sys
import fitz

SRC_DIR = "books"
OUT_DIR = "books_small"

DPI = 90          # lower = smaller file, blurrier
QUALITY = 55      # JPEG quality 1-100


def human(n):
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def compress(path, out_path, dpi, quality):
    src = fitz.open(path)
    out = fitz.open()
    zoom = dpi / 72
    mat = fitz.Matrix(zoom, zoom)
    total = len(src)

    for i, page in enumerate(src):
        pix = page.get_pixmap(matrix=mat)
        img = pix.tobytes("jpeg", jpg_quality=quality)
        new_page = out.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(new_page.rect, stream=img)
        if total > 100 and (i + 1) % 100 == 0:
            print(f"      page {i+1}/{total}")

    out.save(out_path, deflate=True, garbage=4)
    src.close()
    out.close()


def main():
    dpi, quality = DPI, QUALITY
    if len(sys.argv) >= 3:
        try:
            dpi, quality = int(sys.argv[1]), int(sys.argv[2])
        except ValueError:
            print("Usage: python compress_books.py [dpi] [quality]")
            return

    if not os.path.isdir(SRC_DIR):
        print(f"ERROR: '{SRC_DIR}' folder not found.")
        return

    os.makedirs(OUT_DIR, exist_ok=True)
    pdfs = [f for f in os.listdir(SRC_DIR) if f.lower().endswith(".pdf")]
    if not pdfs:
        print("No PDFs found.")
        return

    print(f"Settings: DPI={dpi}, JPEG quality={quality}\n")
    before_total = after_total = 0

    for name in pdfs:
        src_path = os.path.join(SRC_DIR, name)
        out_path = os.path.join(OUT_DIR, name)
        before = os.path.getsize(src_path)
        before_total += before

        print(f"Compressing: {name}  ({human(before)})")
        try:
            compress(src_path, out_path, dpi, quality)
        except Exception as e:
            print(f"   FAILED: {e}  -> copying original instead")
            import shutil
            shutil.copy2(src_path, out_path)

        after = os.path.getsize(out_path)

        # If compression made it bigger, keep the original file instead.
        if after >= before:
            import shutil
            shutil.copy2(src_path, out_path)
            after = before
            print(f"   -> no gain, kept original ({human(after)})")
        else:
            saved = 100 - (after / before * 100)
            print(f"   -> {human(after)}   (saved {saved:.0f}%)")

        after_total += after
        print()

    print("=" * 50)
    print(f"Before: {human(before_total)}")
    print(f"After:  {human(after_total)}")
    print(f"Compressed files are in the '{OUT_DIR}' folder.")
    print("\nIf any single file is still over 100 MB, run again with lower")
    print("settings, e.g.:   python compress_books.py 70 45")


if __name__ == "__main__":
    main()
