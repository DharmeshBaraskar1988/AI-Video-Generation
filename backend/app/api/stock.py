from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..db import StockLog, engine
from ..graphs.stock_agent import ask
from ..services import stock

router = APIRouter(prefix="/api/stock", tags=["stock"])


class ChatBody(BaseModel):
    question: str = Field(min_length=2, max_length=500)


@router.post("/chat")
def chat(body: ChatBody) -> dict:
    return ask(body.question)


@router.get("/companies")
def list_companies() -> list[dict]:
    return [{k: c[k] for k in ("symbol", "code", "name_en", "name_ar", "sector")} for c in stock.companies()]


@router.get("/quote/{symbol}")
def quote(symbol: str) -> dict:
    if not stock.find_by_symbol(symbol):
        raise HTTPException(404, f"Unknown QSE symbol '{symbol}'")
    sym = symbol.upper() if symbol.upper().endswith(".QA") else f"{symbol.upper()}.QA"
    try:
        return stock.get_quote(sym)
    except stock.StockDataError as exc:
        raise HTTPException(503, f"Price source unavailable: {exc}") from exc


@router.get("/log")
def stock_log(limit: int = 50) -> list[StockLog]:
    with Session(engine) as s:
        return list(s.exec(select(StockLog).order_by(StockLog.created_at.desc()).limit(limit)).all())
