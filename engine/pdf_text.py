def extract_pdf_text(path, limit=60000):
    import pymupdf
    chunks, total = [], 0
    with pymupdf.open(path) as doc:
        for number, page in enumerate(doc, 1):
            text = page.get_text("text").strip()
            if text:
                chunk = f"\n--- PAGE {number} ---\n{text}"
                chunks.append(chunk)
                total += len(chunk)
            if total >= limit:
                break
    return "\n".join(chunks)[:limit]
