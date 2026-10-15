"""비상용: yfinance 수집(market.json)이 없을 때 Claude 가 웹페이지에서 읽은 숫자로 market.json 생성.

입력(market_web.json) 형식
{
  "session_date": "2026-10-14",
  "tickers": {"NVDA": {"close": 0, "change_pct": 0, "week_pct": null, "month_pct": null,
                       "target_mean": 0, "target_high": 0, "target_low": 0,
                       "buy": 0, "hold": 0, "sell": 0, "next_earnings": "YYYY-MM-DD"}},
  "indices": {"^GSPC": {"close": 0, "change_pct": 0}}
}
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .analyst import AnalystView
from .config import load_config, load_tickers
from .market_calendar import SessionInfo
from .market_data import Quote
from .store import save_market


def _q(sym: str, name: str, d: dict) -> Quote:
    q = Quote(symbol=sym, name=name)
    q.close, q.change_pct = d.get("close"), d.get("change_pct")
    if q.close is not None and q.change_pct is not None:
        q.prev_close = q.close / (1 + q.change_pct / 100)
        q.change = q.close - q.prev_close
    for k in ("week_pct", "month_pct", "ytd_pct", "next_earnings", "high_52w", "low_52w"):
        if d.get(k) is not None:
            setattr(q, k, d[k])
    return q


def build_from_web(src: Path, out: Path) -> Path:
    cfg = load_config()
    raw = json.loads(src.read_text(encoding="utf-8"))
    tickers = load_tickers(cfg)
    sess = SessionInfo(session=date.fromisoformat(raw["session_date"]), closed_yesterday=False,
                       note="웹페이지 기준 시세(비상 모드)")
    tk = raw.get("tickers", {})
    quotes, views = {}, {}
    for t in tickers:
        d = tk.get(t.symbol, {})
        quotes[t.symbol] = _q(t.symbol, t.label, d)
        v = AnalystView(symbol=t.symbol, target_mean=d.get("target_mean"), target_high=d.get("target_high"),
                        target_low=d.get("target_low"), buy=d.get("buy") or 0, hold=d.get("hold") or 0,
                        sell=d.get("sell") or 0)
        v.n_analysts = (v.buy + v.hold + v.sell) or None
        views[t.symbol] = v
    mcfg = cfg.get("market", {})
    idx_raw = raw.get("indices", {})
    indices = {s: _q(s, n, idx_raw.get(s, {})) for s, n in mcfg.get("indicators", {}).items()}
    futures = {s: _q(s, n, idx_raw.get(s, {})) for s, n in mcfg.get("futures", {}).items()}
    return save_market(out, session=sess, tickers=tickers, quotes=quotes, indices=indices,
                       futures=futures, views=views, source="web")
