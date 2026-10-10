"""Documents (upload -> agent), data reviews (approve / edit extracted figures) and summaries."""
from __future__ import annotations

import hashlib
import io
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pypdf import PdfReader, PdfWriter
from sqlmodel import Session, select

from ..config import settings
from ..db import DataReview, Document, engine
from ..services import doc_agent, rag, summary
from ..services.quarters import PERIOD_RE

router = APIRouter(tags=["documents"])

MAX_UPLOAD_MB = 40


# ---------- documents ----------

@router.get("/api/documents")
def list_documents() -> list[dict]:
    return rag.list_documents()


@router.post("/api/documents/upload")
async def upload(files: list[UploadFile] = File(...)) -> dict:
    """Save the files and start the document agent (classify -> index -> extract) in the background."""
    settings.documents_dir.mkdir(parents=True, exist_ok=True)
    report, new_ids = [], []
    with Session(engine) as s:
        known_hashes = {d.sha256: d for d in s.exec(select(Document)).all() if d.sha256}
    for up in files:
        name = Path(up.filename or "document").name
        suffix = Path(name).suffix.lower()
        if suffix not in rag.SUPPORTED_SUFFIXES:
            report.append({"name": name, "status": "rejected", "reason": "only PDF or Markdown (.md) files"})
            continue
        data = await up.read()
        if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
            report.append({"name": name, "status": "rejected", "reason": f"larger than {MAX_UPLOAD_MB} MB"})
            continue
        digest = hashlib.sha256(data).hexdigest()
        if digest in known_hashes:
            report.append({"name": name, "status": "duplicate", "doc_id": known_hashes[digest].id})
            continue
        stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(name).stem).strip("_")[:60] or "document"
        stored = f"{datetime.now(timezone.utc):%Y%m%d%H%M%S}_{stem}{suffix}"
        (settings.documents_dir / stored).write_bytes(data)
        with Session(engine) as s:
            doc = Document(file=stored, name=name, status="uploaded", sha256="")
            s.add(doc)
            s.commit()
            new_ids.append(doc.id)
            known_hashes[digest] = doc
        report.append({"name": name, "status": "queued", "doc_id": new_ids[-1]})
    if new_ids:
        doc_agent.start_pipeline(new_ids)
    return {"report": report, "documents": rag.list_documents()}


@router.post("/api/documents/scan")
def scan() -> dict:
    """Pick up files copied straight into data/documents, plus documents never classified, and process them."""
    rag.register_folder_files()
    with Session(engine) as s:
        todo = [d.id for d in s.exec(select(Document)).all() if not d.company or d.status in (None, "uploaded")]
    if todo:
        # chunks indexed before documents carried company/period metadata are replaced
        try:
            rag.collection().delete(where={"$and": [{"kind": "document"}, {"company": ""}]})
        except Exception:  # noqa: BLE001
            pass
        doc_agent.start_pipeline(todo)
    return {"queued": todo, "documents": rag.list_documents()}


class DocumentPatch(BaseModel):
    company: str | None = None
    period: str | None = None
    name_en: str | None = None
    name_ar: str | None = None


@router.patch("/api/documents/{doc_id}")
def correct_document(doc_id: int, body: DocumentPatch) -> dict:
    """A person corrects what the agent decided; the document is re-indexed and its figures re-extracted."""
    with Session(engine) as s:
        doc = s.get(Document, doc_id)
        if not doc:
            raise HTTPException(404, "No such document")
        old = (doc.company, doc.period)
        if body.period is not None:
            period = body.period.strip().upper()
            if not PERIOD_RE.match(period):
                raise HTTPException(400, "Period must look like Q2 2026, H1 2026, 9M 2026 or FY 2026")
            doc.period = period
        if body.company is not None:
            doc.company = re.sub(r"[^a-z0-9]", "", body.company.lower())[:12] or doc.company
        meta = dict(doc.meta or {})
        company_meta = dict(meta.get("company") or {})
        company_meta["slug"] = doc.company
        if body.name_en:
            company_meta["name_en"] = body.name_en
        if body.name_ar:
            company_meta["name_ar"] = body.name_ar
        meta["company"], meta["corrected"] = company_meta, True
        doc.meta = meta
        s.add(doc)
        s.commit()
        new = (doc.company, doc.period)
    doc_agent.reindex_group(*new)
    if old != new and all(old):
        doc_agent.reindex_group(*old)
    return {"documents": rag.list_documents()}


@router.post("/api/documents/{doc_id}/reprocess")
def reprocess(doc_id: int) -> dict:
    doc_agent.start_pipeline([doc_id])
    return {"queued": [doc_id]}


@router.delete("/api/documents/{doc_id}")
def delete_document(doc_id: int) -> dict:
    with Session(engine) as s:
        doc = s.get(Document, doc_id)
        if not doc:
            raise HTTPException(404, "No such document")
        group = (doc.company, doc.period)
        rag.unindex_document(doc_id)
        (settings.documents_dir / doc.file).unlink(missing_ok=True)
        s.delete(doc)
        s.commit()
    return {"documents": rag.list_documents(), "group": group}


def _doc_file(doc_id: int) -> tuple[Document, Path]:
    with Session(engine) as s:
        doc = s.get(Document, doc_id)
    if not doc or not (path := settings.documents_dir / doc.file).exists():
        raise HTTPException(404, "No such document")
    return doc, path


@router.get("/api/documents/{doc_id}/download")
def download_document(doc_id: int) -> FileResponse:
    """The whole source document, as an attachment with its original name."""
    doc, path = _doc_file(doc_id)
    return FileResponse(path, filename=doc.name or doc.file)


@router.get("/api/documents/{doc_id}/pages")
def download_pages(doc_id: int, start: int, end: int | None = None) -> Response:
    """Only the cited page(s) of a PDF (1-based, inclusive), so a source can be saved on its own."""
    doc, path = _doc_file(doc_id)
    if path.suffix.lower() != ".pdf":
        raise HTTPException(400, "Page extracts are only available for PDF documents")
    reader = PdfReader(str(path))
    end = end or start
    if not 1 <= start <= end <= len(reader.pages):
        raise HTTPException(400, f"Pages must be within 1-{len(reader.pages)}")
    writer = PdfWriter()
    for i in range(start - 1, end):
        writer.add_page(reader.pages[i])
    buf = io.BytesIO()
    writer.write(buf)
    pages = f"p{start}" if start == end else f"p{start}-{end}"
    name = f"{Path(doc.name or doc.file).stem}_{pages}.pdf"
    return Response(buf.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


@router.get("/api/documents/search")
def search(q: str, k: int = 8, company: str | None = None, period: str | None = None) -> list[dict]:
    return rag.search(q, k=k, where=rag.doc_where(company, period))


# ---------- data reviews ----------

@router.get("/api/reviews")
def reviews() -> list[dict]:
    return doc_agent.list_reviews()


@router.get("/api/reviews/{rid}")
def get_review(rid: str) -> DataReview:
    r = doc_agent.get_review(rid)
    if not r:
        raise HTTPException(404, "No such review")
    return r


class ReviewBody(BaseModel):
    content: dict[str, Any]
    auto_continue: bool = True


@router.put("/api/reviews/{rid}")
def save_review(rid: str, body: ReviewBody) -> DataReview:
    """Save a person's edits without approving."""
    with Session(engine) as s:
        r = s.get(DataReview, rid)
        if not r:
            raise HTTPException(404, "No such review")
        r.content = body.content
        r.updated_at = datetime.now(timezone.utc)
        s.add(r)
        s.commit()
        s.refresh(r)
        return r


@router.post("/api/reviews/{rid}/approve")
def approve_review(rid: str, body: ReviewBody) -> dict:
    r = doc_agent.get_review(rid)
    if not r:
        raise HTTPException(404, "No such review")
    if r.status == "extracting":
        raise HTTPException(409, "Extraction is still running")
    included = [f for f in body.content.get("figures", []) if f.get("include") and f.get("value") is not None]
    if not any(f["period"] == body.content.get("period") for f in included):
        raise HTTPException(400, "Include at least one figure for the target period before approving")
    return doc_agent.approve(rid, body.content, auto_continue=body.auto_continue)


@router.post("/api/reviews/{rid}/extract")
def re_extract(rid: str) -> dict:
    r = doc_agent.get_review(rid)
    if not r:
        raise HTTPException(404, "No such review")
    doc_agent.reindex_group(r.company, r.period)
    return {"started": True}


# ---------- summaries ----------

@router.get("/api/summary")
def get_summary(company: str | None = None, period: str | None = None) -> dict:
    options = summary.available()
    if not company or not period:
        chosen = next((o for o in options if o["has_summary"]), options[0] if options else None)
        company, period = (chosen["company"], chosen["period"]) if chosen else (None, None)
    return {
        "options": options,
        "company": company,
        "period": period,
        "state": summary.state(company, period) if company else {"status": "idle"},
        "summary": summary.load(company, period) if company else None,
    }


class SummaryBody(BaseModel):
    company: str
    period: str


@router.post("/api/summary")
def generate_summary(body: SummaryBody) -> dict:
    started = summary.run_in_background(body.company, body.period)
    return {"started": started, "state": summary.state(body.company, body.period)}
