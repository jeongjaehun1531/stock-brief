"""시세 수집 (yfinance, 무료)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

log = logging.getLogger(__name__)


@dataclass
class Quote:
    symbol: str
    name: str = ""
    close: float | None = None
    prev_close: float | None = None
    change: float | None = None
    change_pct: float | None = None
    week_pct: float | None = None       # 5거래일
    month_pct: float | None = None      # 21거래일
    ytd_pct: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    volume: float | None = None
    volume_ratio: float | None = None   # 당일 거래량 / 20일 평균
    spark: list[float] = field(default_factory=list)  # 최근 30거래일 종가
    as_of: date | None = None
    market_cap: float | None = None
    next_earnings: str | None = None
    error: str | None = None

    @property
    def up(self) -> bool | None:
        return None if self.change is None else self.change >= 0


def _pct(a, b):
    try:
        return (a / b - 1) * 100 if a is not None and b else None
    except Exception:
        return None


def _quote_from_frame(symbol: str, df: pd.DataFrame, session: date) -> Quote:
    q = Quote(symbol=symbol)
    df = df.dropna(subset=["Close"])
    df = df[df.index.date <= session] if len(df) else df
    if len(df) < 2:
        q.error = "시세 없음"
        return q
    c = df["Close"]
    q.as_of = df.index[-1].date()
    q.close, q.prev_close = float(c.iloc[-1]), float(c.iloc[-2])
    q.change = q.close - q.prev_close
    q.change_pct = _pct(q.close, q.prev_close)
    q.week_pct = _pct(q.close, float(c.iloc[-6])) if len(c) > 5 else None
    q.month_pct = _pct(q.close, float(c.iloc[-22])) if len(c) > 21 else None
    ytd = c[c.index.year == q.as_of.year]
    prev_year = c[c.index.year < q.as_of.year]
    if len(prev_year):
        q.ytd_pct = _pct(q.close, float(prev_year.iloc[-1]))
    elif len(ytd):
        q.ytd_pct = _pct(q.close, float(ytd.iloc[0]))
    last_year = df.iloc[-252:]
    q.high_52w = float(last_year["High"].max())
    q.low_52w = float(last_year["Low"].min())
    if "Volume" in df and df["Volume"].iloc[-1] > 0:
        q.volume = float(df["Volume"].iloc[-1])
        avg = df["Volume"].iloc[-21:-1].mean()
        q.volume_ratio = q.volume / avg if avg else None
    q.spark = [round(float(x), 4) for x in c.iloc[-30:]]
    return q


def fetch_quotes(symbols: dict[str, str], session: date) -> dict[str, Quote]:
    """symbols: {티커: 표시명}. 한 번의 다운로드로 일괄 수집."""
    import yfinance as yf

    syms = list(symbols)
    out: dict[str, Quote] = {}
    try:
        data = yf.download(
            syms, period="13mo", interval="1d", group_by="ticker",
            auto_adjust=False, progress=False, threads=True,
        )
    except Exception as e:
        log.error("yfinance 다운로드 실패: %s", e)
        data = None
    for s in syms:
        try:
            df = data[s] if data is not None and len(syms) > 1 else data
            q = _quote_from_frame(s, df, session)
        except Exception as e:
            q = Quote(symbol=s, error=f"시세 오류: {e}")
        q.name = symbols[s]
        if q.as_of and q.as_of != session:
            log.warning("%s 마지막 시세일 %s ≠ 대상 거래일 %s", s, q.as_of, session)
        out[s] = q
    return out


def enrich_stock_info(q: Quote) -> None:
    """개별 종목 부가정보: 시가총액, 다음 실적발표일."""
    import yfinance as yf

    t = yf.Ticker(q.symbol)
    try:
        q.market_cap = float(t.fast_info.get("marketCap") or 0) or None
    except Exception:
        pass
    try:
        cal = t.calendar or {}
        ed = cal.get("Earnings Date") if isinstance(cal, dict) else None
        if ed:
            first = ed[0] if isinstance(ed, (list, tuple)) else ed
            q.next_earnings = pd.Timestamp(first).strftime("%Y-%m-%d")
    except Exception:
        pass
