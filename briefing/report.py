"""수집·분석 결과 → 템플릿 컨텍스트 → HTML."""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .analyst import ACTION_KO, AnalystView
from .config import ROOT, Ticker
from .market_data import Quote

WEEKDAY_KO = "월화수목금토일"


# ── 포맷 헬퍼 (템플릿 필터) ───────────────────────────────
def f_price(x, nd=2):
    return "–" if x is None else f"{x:,.{nd}f}"


def f_pct(x, nd=2):
    if x is None:
        return "–"
    r = round(x, nd)
    arrow = "▲" if r > 0 else ("▼" if r < 0 else "")
    return f"{arrow}{abs(r):.{nd}f}%"


def f_signed(x, nd=2):
    return "–" if x is None else f"{x:+,.{nd}f}"


def tone(x):
    """한국식 색상: 상승=빨강, 하락=파랑"""
    if x is None or abs(x) < 0.005:
        return "flat"
    return "up" if x > 0 else "down"


def f_cap(x):
    if not x:
        return "–"
    if x >= 1e12:
        return f"${x / 1e12:.2f}T"
    return f"${x / 1e9:.0f}B"


def kdate(d: date) -> str:
    return f"{d.month}/{d.day}({WEEKDAY_KO[d.weekday()]})"


# ── 시각화 데이터 ─────────────────────────────────────────
def sparkline(values: list[float], w=220, h=56, pad=4) -> dict | None:
    if not values or len(values) < 2:
        return None
    lo, hi = min(values), max(values)
    rng = (hi - lo) or 1
    n = len(values)
    pts = [
        (pad + i * (w - 2 * pad) / (n - 1), pad + (hi - v) * (h - 2 * pad) / rng)
        for i, v in enumerate(values)
    ]
    line = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = line + f" L{pts[-1][0]:.1f},{h} L{pts[0][0]:.1f},{h} Z"
    return {"w": w, "h": h, "line": line, "area": area,
            "last": pts[-1], "tone": tone(values[-1] - values[0])}


def target_bar(price: float | None, av: AnalystView) -> dict | None:
    """최저~최고 목표가 막대 위에 현재가·평균 목표가 위치(%)"""
    lo, hi, mean = av.target_low, av.target_high, av.target_mean
    if not (lo and hi and mean and price):
        return None
    lo2, hi2 = min(lo, price), max(hi, price)
    span = (hi2 - lo2) or 1
    pos = lambda v: round((v - lo2) / span * 100, 1)  # noqa: E731
    return {"low": lo, "high": hi, "mean": mean, "price": price,
            "p_low": pos(lo), "p_high": pos(hi), "p_mean": pos(mean), "p_price": pos(price),
            "upside": (mean / price - 1) * 100}


def build_context(*, session_info, report_dt: datetime, tickers: list[Ticker],
                  quotes: dict[str, Quote], indices: dict[str, Quote], futures: dict[str, Quote],
                  views: dict[str, AnalystView], ai_tickers: dict[str, dict], news: dict,
                  weekly: bool = False, week_ahead: dict | None = None) -> dict:
    stocks = []
    for t in tickers:
        q = quotes[t.symbol]
        av = views.get(t.symbol) or AnalystView(symbol=t.symbol)
        ai = ai_tickers.get(t.symbol, {})
        actions = [asdict(a) | {"action_ko": ACTION_KO.get(a.action, a.action)} for a in av.actions]
        # Claude 가 웹검색으로 찾은 추가 액션 (yfinance 에 없는 것만)
        known = {(a["firm"].lower()[:6], a["date"]) for a in actions}
        for x in ai.get("extra_actions") or []:
            key = (str(x.get("firm", "")).lower()[:6], x.get("date"))
            if key not in known and x.get("firm"):
                actions.append({"date": x.get("date", ""), "firm": x.get("firm"), "rating": x.get("rating", ""),
                                "from_rating": "", "target": x.get("target") or None,
                                "prior_target": x.get("prior_target") or None, "major": True,
                                "action_ko": "", "note": x.get("note", ""), "web": True})
        stocks.append({
            "t": t, "q": q, "av": av, "ai": ai,
            "spark": sparkline(q.spark),
            "bar": target_bar(q.close, av),
            "actions": actions[:6],
            "upside": av.upside(q.close),
            "consensus_total": (av.buy + av.hold + av.sell) or None,
        })

    up = sum(1 for s in stocks if (s["q"].change_pct or 0) > 0)
    return {
        "report_date": f"{report_dt:%Y.%m.%d} ({WEEKDAY_KO[report_dt.weekday()]})",
        "session": session_info.session,
        "session_label": f"미국 {kdate(session_info.session)} 종가 기준" + (" · 지난주 결산" if weekly else ""),
        "weekly": weekly,
        "week_ahead": week_ahead or {},
        "my_symbols": [t.symbol for t in tickers],
        "session_note": session_info.note,
        "indices": list(indices.values()),
        "futures": list(futures.values()),
        "news": news,
        "stocks": stocks,
        "breadth": {"up": up, "down": len(stocks) - up},
        "generated_at": f"{report_dt:%H:%M}",
    }


def render_html(ctx: dict, mode: str = "cards") -> str:
    env = Environment(
        loader=FileSystemLoader(str(ROOT / "templates")),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True, lstrip_blocks=True,
    )
    env.filters.update(price=f_price, pct=f_pct, signed=f_signed, tone=tone, cap=f_cap)
    return env.get_template("report.html.j2").render(**ctx, mode=mode)


def save_html(html: str, out_dir: Path, name: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / name
    p.write_text(html, encoding="utf-8")
    return p
