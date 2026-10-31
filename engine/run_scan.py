
import csv,json,hashlib,logging
from datetime import datetime,timezone
from .config import DATA,LOGS,DOWNLOADS,load_sources
from .collector import fetch_source,download_pdf
from .pdf_text import extract_pdf_text
from .ai_extract import extract_with_ai
from .dedupe import load_seen,seen,mark
logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s",
 handlers=[logging.FileHandler(LOGS/"latest_scan.log",encoding="utf-8"),logging.StreamHandler()])
log=logging.getLogger("job-alert")
def main():
    sp=DATA/"seen_items.json"; qp=DATA/"review_queue.json"
    state=load_seen(sp); queue=json.loads(qp.read_text()) if qp.exists() else []
    ids={x["id"] for x in queue}; added=0
    for source in load_sources():
        if not source.get("enabled"): continue
        try: items=fetch_source(source)
        except Exception as e: log.exception("Source failed %s: %s",source["name"],e); continue
        for item in items:
            try:
                digest=None; local=None
                if item["kind"]=="pdf":
                    local,digest=download_pdf(item,DOWNLOADS); body=extract_pdf_text(local)
                    draft=extract_with_ai(body,item["title"],item["url"])
                else:
                    body=f"Discovered web page: {item['title']}\\n{item['url']}"
                    draft={"status":"needs_source_adapter","raw_text_excerpt":body}
                if seen(item,digest,state): continue
                ident=hashlib.sha256((item["url"]+(digest or "")).encode()).hexdigest()[:16]
                if ident in ids: mark(item,digest,state); continue
                queue.append({"id":ident,"detected_at_utc":datetime.now(timezone.utc).isoformat(),
                  "source_name":item["source_name"],"source_page":item["source_url"],
                  "candidate_title":item["title"],"candidate_url":item["url"],
                  "document_sha256":digest,"local_pdf":str(local.relative_to(DATA)) if local else None,
                  "review_status":"pending_review","human_verified":False,"ai_draft":draft})
                ids.add(ident); mark(item,digest,state); added+=1
            except Exception as e: log.exception("Candidate failed %s: %s",item.get("url"),e)
    qp.write_text(json.dumps(queue,indent=2,ensure_ascii=False),encoding="utf-8")
    sp.write_text(json.dumps(state,indent=2),encoding="utf-8")
    cols=["id","detected_at_utc","source_name","candidate_title","candidate_url","review_status","human_verified","notice_type","organisation","advertisement_number","vacancy_count","application_end_date"]
    with (DATA/"review_queue.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=cols); w.writeheader()
        for x in queue:
            d=x.get("ai_draft",{})
            w.writerow({**{k:x.get(k) for k in cols[:7]},**{k:d.get(k) for k in cols[7:]}})
    log.info("Scan complete. New candidates=%s; queue total=%s",added,len(queue))
if __name__=="__main__": main()
