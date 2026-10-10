from fastapi import APIRouter, HTTPException

from ..services import quarters as svc

router = APIRouter(prefix="/api/quarters", tags=["quarters"])


@router.get("")
def list_quarters() -> dict:
    files, errors = svc.load_all()
    return {"companies": [svc.company_view(qf) for qf in files.values()], "errors": errors}


@router.get("/{company}/{period}")
def get_quarter(company: str, period: str) -> dict:
    found = svc.get_quarter(company, period)
    if not found:
        raise HTTPException(404, f"No quarter '{period}' for company '{company}'")
    qf, q = found
    return {
        "company": svc.company_view(qf) | {"quarters": None},
        "quarter": svc.quarter_view(qf, q),
        "history_net_profit": [h.model_dump() for h in qf.history_net_profit],
        "narrative_drivers": qf.narrative_drivers,
        "source_documents": qf.source_documents,
    }
