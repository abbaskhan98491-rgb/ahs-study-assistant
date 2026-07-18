"""
Free RAG System for Semester Books (Weak Laptop - Groq API)
DETAILED ANSWERS + BOOK SELECTION
============================================================
Setup (run once):
    pip install pymupdf sentence-transformers chromadb groq

Usage:
    1. Paste your Groq API key below (PASTE-YOUR-KEY-HERE)
    2. Put PDFs in a folder called "books/"
    3. python rag_pipeline.py index    -> build database (run once)
    4. python rag_pipeline.py ask      -> ask questions
"""

import os
import sys
import fitz
import chromadb
from sentence_transformers import SentenceTransformer

# ---------- PASTE YOUR KEY HERE (keep the quotes) ----------
GROQ_API_KEY = ""
# ------------------------------------------------------------

BOOKS_DIR = "books"
DB_DIR = "rag_db"
COLLECTION_NAME = "semester_books"

EMBED_MODEL = "all-MiniLM-L6-v2"
CHUNK_SIZE = 400
CHUNK_OVERLAP = 60
TOP_K = 10
GROQ_MODEL = "llama-3.3-70b-versatile"


def extract_pdf(path):
    doc = fitz.open(path)
    pages = []
    for i, page in enumerate(doc):
        text = page.get_text().strip()
        has_images = len(page.get_images()) > 0
        if text:
            pages.append((i + 1, text, has_images))
    doc.close()
    return pages


def check_pdf_is_text_based(path):
    doc = fitz.open(path)
    sample = min(5, len(doc))
    total_chars = sum(len(doc[i].get_text()) for i in range(sample))
    doc.close()
    return total_chars > 200


def chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        chunk = " ".join(words[start:start + size])
        if chunk.strip():
            chunks.append(chunk)
        start += size - overlap
    return chunks


def build_index():
    if not os.path.isdir(BOOKS_DIR):
        print(f"ERROR: Create a folder named '{BOOKS_DIR}' and put your PDFs inside.")
        return
    pdfs = [f for f in os.listdir(BOOKS_DIR) if f.lower().endswith(".pdf")]
    if not pdfs:
        print(f"ERROR: No PDFs found in '{BOOKS_DIR}/'.")
        return

    print(f"Loading embedding model ({EMBED_MODEL})...")
    embedder = SentenceTransformer(EMBED_MODEL)

    client = chromadb.PersistentClient(path=DB_DIR)
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.create_collection(COLLECTION_NAME)

    doc_id = 0
    for pdf in pdfs:
        path = os.path.join(BOOKS_DIR, pdf)
        if not check_pdf_is_text_based(path):
            print(f"WARNING: '{pdf}' looks SCANNED. Skipping (needs OCR).")
            continue
        print(f"Processing: {pdf}")
        pages = extract_pdf(path)
        all_chunks, all_metas, all_ids = [], [], []
        for page_num, text, has_images in pages:
            for chunk in chunk_text(text):
                all_chunks.append(chunk)
                all_metas.append({"book": pdf, "page": page_num, "has_diagram": has_images})
                all_ids.append(f"doc_{doc_id}")
                doc_id += 1
        BATCH = 64
        for i in range(0, len(all_chunks), BATCH):
            batch = all_chunks[i:i + BATCH]
            embeddings = embedder.encode(batch, show_progress_bar=False).tolist()
            collection.add(
                documents=batch,
                embeddings=embeddings,
                metadatas=all_metas[i:i + BATCH],
                ids=all_ids[i:i + BATCH],
            )
        print(f"  -> {len(all_chunks)} chunks indexed")
    print(f"\nDone. Total chunks in DB: {collection.count()}")


def pick_book(book_names):
    """Let user choose which book to search."""
    print("\nWhich book should I answer from?")
    for i, name in enumerate(book_names, start=1):
        print(f"  {i}. {name}")
    print(f"  {len(book_names) + 1}. Both / All books")
    choice = input("Enter number (default = All): ").strip()

    if not choice:
        return None  # None = search all
    try:
        n = int(choice)
        if 1 <= n <= len(book_names):
            return book_names[n - 1]
        return None  # anything else = all
    except ValueError:
        return None


def ask_loop():
    if GROQ_API_KEY == "PASTE-YOUR-KEY-HERE" or not GROQ_API_KEY.strip():
        print("ERROR: Paste your Groq API key at the top of this file.")
        return
    try:
        from groq import Groq
    except ImportError:
        print("ERROR: run ->  pip install groq")
        return

    groq_client = Groq(api_key=GROQ_API_KEY)
    print(f"Loading embedding model ({EMBED_MODEL})...")
    embedder = SentenceTransformer(EMBED_MODEL)

    client = chromadb.PersistentClient(path=DB_DIR)
    try:
        collection = client.get_collection(COLLECTION_NAME)
    except Exception:
        print("ERROR: No index found. Run 'python rag_pipeline.py index' first.")
        return

    # Find the list of books in the database
    sample = collection.get(limit=10000, include=["metadatas"])
    book_names = sorted({m["book"] for m in sample["metadatas"]})

    print("\nAsk questions about your books. Type 'exit' to quit.")

    while True:
        # Choose book each round
        selected_book = pick_book(book_names)
        if selected_book:
            print(f"[Answering from: {selected_book}]")
        else:
            print("[Answering from: ALL books]")

        question = input("Q: ").strip()
        if not question or question.lower() in ("exit", "quit"):
            break

        q_emb = embedder.encode([question]).tolist()

        # Filter by book if one was chosen
        query_args = {"query_embeddings": q_emb, "n_results": TOP_K}
        if selected_book:
            query_args["where"] = {"book": selected_book}

        results = collection.query(**query_args)
        chunks = results["documents"][0]
        metas = results["metadatas"][0]

        if not chunks:
            print("\nNo matching text found in that book. Try 'Both'.\n")
            continue

        context = "\n\n---\n\n".join(
            f"[{m['book']}, page {m['page']}]\n{c}" for c, m in zip(chunks, metas)
        )

        prompt = f"""You are a medical study tutor. Answer the student's question in DETAIL,
using ONLY the context provided below from their textbooks.

Rules:
- Write a full, well-structured explanation, like a textbook or exam answer.
- Use clear headings and bullet points where helpful.
- Define key terms, explain the mechanism/process step by step, and mention
  clinical or functional significance if present in the context.
- Cite the book name and page number for the main points.
- If the context is not enough, say what is missing instead of inventing facts.
- Do NOT add information that is not in the context.

CONTEXT:
{context}

QUESTION: {question}

DETAILED ANSWER:"""

        try:
            response = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2000,
            )
            print("\n" + "=" * 60)
            print(response.choices[0].message.content)
            print("=" * 60)
        except Exception as e:
            print(f"\nERROR talking to Groq: {e}")
            continue

        print("\nSources used:")
        diagram_pages = []
        for m in metas:
            flag = "  <-- has a diagram" if m.get("has_diagram") else ""
            print(f"  - {m['book']}, page {m['page']}{flag}")
            if m.get("has_diagram"):
                diagram_pages.append((m['book'], m['page']))
        if diagram_pages:
            print("\nDiagrams to look at (open the PDF to these pages):")
            seen = set()
            for book, page in diagram_pages:
                if (book, page) not in seen:
                    print(f"  * {book} - page {page}")
                    seen.add((book, page))
        print()


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("index", "ask"):
        print(__doc__)
    elif sys.argv[1] == "index":
        build_index()
    else:
        ask_loop()
