"""증권사 목표가·투자의견 수집 (yfinance).

- 컨센서스: 평균/중간/최고/최저 목표가, 매수·보유·매도 비율
- 최근 N일 목표가 변경 이력 중 '주요 증권사'만 추려 표시
  (주요 증권사 액션이 없으면 다른 증권사 액션으로 보충하고 표시)
- Claude 분석 단계에서 웹검색으로 최신 리포트 코멘트를 추가로 붙임
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

log = logging.getLogger(__name__)


@dataclass
class AnalystAction:
    date: str
    firm: str
    action: str          # up / down / main / init / reit
    rating: str          # 현재 등급
    from_rating: str = ""
    target: float | None = None
    prior_target: float | None = None
    major: bool = True


@dataclass
class AnalystView:
    symbol: str
    target_mean: float | None = None
    target_median: float | None = None
    target_high: float | None = None
    target_low: float | None = None
    n_analysts: int | None = None
    buy: int = 0
    hold: int = 0
    sell: int = 0
    actions: list[AnalystAction] = field(default_factory=list)
    error: str | None = None

    def upside(self, price: float | None) -> float | None:
        if price and self.target_mean:
            return (self.target_mean / price - 1) * 100
        return None


ACTION_KO = {
    "up": "상향", "down": "하향", "init": "신규", "main": "유지", "reit": "재확인",
}


def _is_major(firm: str, majors: list[str]) -> bool:
    f = firm.lower()
    return any(m.lower() in f for m in majors)


def _norm_action(pt_action, grade_action) -> str:
    """priceTargetAction(Raises/Lowers/Maintains/Announces…) 우선, 없으면 등급 Action."""
    p = str(pt_action or "").lower()
    if p.startswith("rais"):
        return "up"
    if p.startswith("lower"):
        return "down"
    if p.startswith("announc") or p.startswith("init"):
        return "init"
    g = str(grade_action or "").lower()
    if g in ACTION_KO:
        return g
    return "main"


def _num(x):
    try:
        v = float(x)
        return v if v > 0 else None
    except Exception:
        return None


def fetch_analyst_view(symbol: str, session: date, cfg: dict) -> AnalystView:
    import yfinance as yf

    acfg = cfg.get("analyst", {})
    majors = acfg.get("major_firms", [])
    lookback = int(acfg.get("lookback_days", 30))
    limit = int(acfg.get("max_actions_per_ticker", 5))

    v = AnalystView(symbol=symbol)
    t = yf.Ticker(symbol)

    try:
        pt = t.analyst_price_targets or {}
        v.target_mean = _num(pt.get("mean"))
        v.target_median = _num(pt.get("median"))
        v.target_high = _num(pt.get("high"))
        v.target_low = _num(pt.get("low"))
    except Exception as e:
        log.info("%s 목표가 컨센서스 없음: %s", symbol, e)

    try:
        rs = t.recommendations_summary
        if isinstance(rs, pd.DataFrame) and len(rs):
            row = rs.iloc[0]
            v.buy = int(row.get("strongBuy", 0) + row.get("buy", 0))
            v.hold = int(row.get("hold", 0))
            v.sell = int(row.get("sell", 0) + row.get("strongSell", 0))
            v.n_analysts = v.buy + v.hold + v.sell or None
    except Exception as e:
        log.info("%s 투자의견 분포 없음: %s", symbol, e)

    try:
        ud = t.upgrades_downgrades
        if isinstance(ud, pd.DataFrame) and len(ud):
            ud = ud.copy()
            ud.index = pd.to_datetime(ud.index)
            since = pd.Timestamp(session - timedelta(days=lookback))
            if ud.index.tz is not None:
                since = since.tz_localize(ud.index.tz)
            recent = ud[ud.index >= since].sort_index(ascending=False)
            rows = []
            for ts, r in recent.iterrows():
                firm = str(r.get("Firm", "")).strip()
                rows.append(AnalystAction(
                    date=ts.strftime("%m/%d"),
                    firm=firm,
                    action=_norm_action(r.get("priceTargetAction"), r.get("Action")),
                    rating=str(r.get("ToGrade", "") or ""),
                    from_rating=str(r.get("FromGrade", "") or ""),
                    target=_num(r.get("currentPriceTarget")),
                    prior_target=_num(r.get("priorPriceTarget")),
                    major=_is_major(firm, majors),
                ))
            major = [a for a in rows if a.major]
            others = [a for a in rows if not a.major]
            v.actions = (major + others)[:limit]
    except Exception as e:
        log.info("%s 증권사 액션 없음: %s", symbol, e)
    return v
