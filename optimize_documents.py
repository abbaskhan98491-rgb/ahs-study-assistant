"""Create smaller display PDFs without removing text or changing page numbers.

Original files stay in books_small; app.py prefers the verified output copies.
Requires PyMuPDF 1.26.1 or newer. Run: python optimize_documents.py
"""
from pathlib import Path
import json
import shutil
import pymupdf


def main():
    source = Path('books_small')
    target = Path('books_optimized')
    target.mkdir(exist_ok=True)
    report = []
    for path in sorted(source.glob('*.pdf')):
        output = target / path.name
        temporary = target / (path.stem + '.tmp.pdf')
        before = path.stat().st_size
        with pymupdf.open(path) as doc:
            count = len(doc)
            samples = sorted({0, count // 2, count - 1})
            texts = [doc[i].get_text() for i in samples]
            sizes = [tuple(doc[i].rect) for i in samples]
            # Retain text, vectors, bookmarks and black/white scan images.
            doc.rewrite_images(dpi_threshold=160, dpi_target=140,
                               quality=75, bitonal=False)
            doc.save(temporary, garbage=4, deflate=True,
                     deflate_images=True, deflate_fonts=True)
        with pymupdf.open(temporary) as checked:
            assert len(checked) == count, path.name
            assert [checked[i].get_text() for i in samples] == texts, path.name
            assert [tuple(checked[i].rect) for i in samples] == sizes, path.name
            for i in samples:
                checked[i].get_pixmap(matrix=pymupdf.Matrix(0.5, 0.5))
        if temporary.stat().st_size < before:
            temporary.replace(output)
        else:
            temporary.unlink()
            shutil.copy2(path, output)
        after = output.stat().st_size
        report.append(dict(file=path.name, pages=count, before=before, after=after))
        print(f'{path.name}: {before / 1048576:.1f} -> {after / 1048576:.1f} MB', flush=True)
    (target / 'compression_report.json').write_text(json.dumps(report, indent=2))
    print(f'Total: {sum(r["before"] for r in report) / 1048576:.1f} -> '
          f'{sum(r["after"] for r in report) / 1048576:.1f} MB', flush=True)


if __name__ == '__main__':
    main()
