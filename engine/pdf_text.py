
import fitz
def extract_pdf_text(path, limit=60000):
    parts=[]
    with fitz.open(path) as doc:
        for i,page in enumerate(doc,1):
            t=page.get_text("text").strip()
            if t: parts.append(f"\\n--- PAGE {i} ---\\n{t}")
            if sum(map(len,parts)) >= limit: break
    return "\\n".join(parts)[:limit]
