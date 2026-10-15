"""단계 간 데이터 교환 파일 (저장소의 data/<KST 날짜>/ 폴더).

  market.json    ← GitHub Actions(collect)가 yfinance 로 작성 (숫자 = 정답)
  analysis.json  ← Claude 예약 작업이 ANALYST.md 지침대로 작성 (해석)
  sent.txt       ← deliver 가 전송 후 기록 (중복 전송 방지)
"""
from __future__ import annotations

import json
from dataclasses import asdict, fields
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .analyst import AnalystAction, AnalystView
from .config import ROOT
from .market_calendar import SessionInfo
from .market_data import Quote

KST = ZoneInfo("Asia/Seoul")


def today_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def day_dir(day: str | None = None) -> Path:
    return ROOT / "data" / (day or today_kst())


# ── 직렬화 ────────────────────────────────────────────────
def _quote_to_dict(q: Quote) -> dict:
    d = asdict(q)
    d["as_of"] = q.as_of.isoformat() if q.as_of else None
    return d


def _quote_from_dict(d: dict) -> Quote:
    names = {f.name for f in fields(Quote)}
    d = {k: v for k, v in d.items() if k in names}
    if d.get("as_of"):
        d["as_of"] = date.fromisoformat(d["as_of"])
    return Quote(**d)


def _view_from_dict(d: dict) -> AnalystView:
    names = {f.name for f in fields(AnalystView)}
    acts = [AnalystAction(**a) for a in d.get("actions", [])]
    d = {k: v for k, v in d.items() if k in names and k != "actions"}
    return AnalystView(**d, actions=acts)


def save_market(path: Path, *, session: SessionInfo, tickers, quotes, indices, futures, views,
                source: str = "yfinance") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "source": source,
        "session": {"date": session.session.isoformat(), "closed_yesterday": session.closed_yesterday,
                    "note": session.note},
        "tickers": [{"symbol": t.symbol, "name": t.name, "memo": t.memo} for t in tickers],
        "quotes": {k: _quote_to_dict(v) for k, v in quotes.items()},
        "indices": {k: _quote_to_dict(v) for k, v in indices.items()},
        "futures": {k: _quote_to_dict(v) for k, v in futures.items()},
        "analyst": {k: asdict(v) for k, v in views.items()},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def load_market(path: Path) -> dict:
    from .config import Ticker

    raw = json.loads(path.read_text(encoding="utf-8"))
    s = raw["session"]
    return {
        "session": SessionInfo(session=date.fromisoformat(s["date"]),
                               closed_yesterday=s.get("closed_yesterday", False), note=s.get("note", "")),
        "tickers": [Ticker(**t) for t in raw["tickers"]],
        "quotes": {k: _quote_from_dict(v) for k, v in raw["quotes"].items()},
        "indices": {k: _quote_from_dict(v) for k, v in raw["indices"].items()},
        "futures": {k: _quote_from_dict(v) for k, v in raw.get("futures", {}).items()},
        "views": {k: _view_from_dict(v) for k, v in raw.get("analyst", {}).items()},
        "source": raw.get("source", "yfinance"),
    }


def load_analysis(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
