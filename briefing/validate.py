"""analysis.json 형식 검사. Claude 예약 작업이 push 전에 반드시 실행."""
from __future__ import annotations

import json
from pathlib import Path

STANCES = {"긍정", "중립", "부정"}
PLAN_HOLD = {"비중 확대 검토", "보유 유지", "비중 축소 검토"}
PLAN_WATCH = {"분할 진입 검토", "관망", "진입 보류"}
LEVEL_LABELS = {"지지", "저항", "목표"}
MOAT_STATUS = {"이상 없음", "주의", "경고"}
THREAT_TYPES = {"경쟁", "기술대체", "고객이탈", "규제", "공급망", "기타"}
SEVERITY = {"낮음", "중간", "높음"}


def _check_moat(p: str, mw) -> list[str]:
    if not isinstance(mw, dict):
        return [f"{p}.moat_watch 없음"]
    errs = []
    if not isinstance(mw.get("moat"), str) or not mw["moat"].strip():
        errs.append(f"{p}.moat_watch.moat 비어있음")
    if mw.get("status") not in MOAT_STATUS:
        errs.append(f"{p}.moat_watch.status 는 {sorted(MOAT_STATUS)} 중 하나")
    th = mw.get("threats")
    if not isinstance(th, list) or len(th) > 3:
        errs.append(f"{p}.moat_watch.threats 는 0~3개 리스트")
        th = []
    for i, x in enumerate(th):
        q = f"{p}.moat_watch.threats[{i}]"
        if not isinstance(x, dict) or not x.get("issue"):
            errs.append(f"{q}.issue 비어있음")
            continue
        if x.get("type") not in THREAT_TYPES:
            errs.append(f"{q}.type 은 {sorted(THREAT_TYPES)} 중 하나")
        if x.get("severity") not in SEVERITY:
            errs.append(f"{q}.severity 는 {sorted(SEVERITY)} 중 하나")
        if not isinstance(x.get("new"), bool):
            errs.append(f"{q}.new 는 true/false")
    has_new = any(isinstance(x, dict) and x.get("new") for x in th)
    if mw.get("status") in ("주의", "경고") and not has_new:
        errs.append(f"{p}.moat_watch.status 가 {mw.get('status')} 이면 new: true 인 위협이 1개 이상 있어야 함")
    if mw.get("status") == "이상 없음" and any(isinstance(x, dict) and x.get("new") and x.get("severity") == "높음" for x in th):
        errs.append(f"{p}.moat_watch: 심각도 '높음' 신규 위협이 있으면 status 는 '이상 없음' 일 수 없음")
    if not mw.get("verdict"):
        errs.append(f"{p}.moat_watch.verdict 비어있음")
    return errs


def _anchor_prices(m: dict, sym: str) -> list[float]:
    """대응 방안 가격으로 허용되는 market.json 숫자들."""
    q = (m.get("quotes") or {}).get(sym) or {}
    av = (m.get("analyst") or {}).get(sym) or {}
    keys_q = ("ma20", "ma50", "ma200", "low_52w", "high_52w", "close")
    keys_a = ("target_low", "target_mean", "target_median", "target_high")
    vals = [q.get(k) for k in keys_q] + [av.get(k) for k in keys_a]
    vals += [a.get("target") for a in av.get("actions") or []]
    return [float(v) for v in vals if isinstance(v, (int, float)) and v > 0]


def _near(price: float, vals: list[float], tol: float = 0.015) -> bool:
    return any(v and abs(price - v) / v <= tol for v in vals)


def _check_plan(p: str, plan, holding: bool | None, anchors: list[float],
                close: float | None = None, targets: list[float] | None = None) -> list[str]:
    errs = []
    if not isinstance(plan, dict):
        return [f"{p}.action_plan 없음"]
    allowed = PLAN_HOLD if holding else PLAN_WATCH if holding is not None else PLAN_HOLD | PLAN_WATCH
    if plan.get("stance") not in allowed:
        errs.append(f"{p}.action_plan.stance 는 {sorted(allowed)} 중 하나")
    for k in ("summary", "if_up", "if_down"):
        if not isinstance(plan.get(k), str) or not plan[k].strip():
            errs.append(f"{p}.action_plan.{k} 비어있음")
    lv = plan.get("levels") or []
    if not isinstance(lv, list) or len(lv) > 3:
        errs.append(f"{p}.action_plan.levels 는 0~3개 리스트")
        lv = []
    for i, x in enumerate(lv):
        if x.get("label") not in LEVEL_LABELS:
            errs.append(f"{p}.action_plan.levels[{i}].label 은 {LEVEL_LABELS} 중 하나")
        price = x.get("price")
        if not isinstance(price, (int, float)):
            errs.append(f"{p}.action_plan.levels[{i}].price 는 숫자")
        elif anchors and not _near(price, anchors):
            errs.append(f"{p}.action_plan.levels[{i}].price {price} 는 market.json 의 이동평균·52주 고저·목표가 어느 것과도 맞지 않음")
        elif close and x.get("label") == "지지" and not (close * 0.7 <= price <= close * 1.005):
            errs.append(f"{p}.action_plan.levels[{i}] 지지 {price} 는 현재가 {close:.2f} 아래 30% 이내여야 함 (없으면 빼기)")
        elif close and x.get("label") == "저항" and not (close * 0.995 <= price <= close * 1.3):
            errs.append(f"{p}.action_plan.levels[{i}] 저항 {price} 는 현재가 {close:.2f} 위 30% 이내여야 함 (없으면 빼기)")
        elif x.get("label") == "목표" and targets is not None and not _near(price, targets):
            errs.append(f"{p}.action_plan.levels[{i}] 목표 {price} 는 증권사 평균/중간 목표가여야 함")
        if not x.get("basis"):
            errs.append(f"{p}.action_plan.levels[{i}].basis 비어있음")
    return errs
IMPACTS = {"상승", "하락", "혼조"}


def validate(analysis_path: Path, market_path: Path | None = None) -> list[str]:
    errs: list[str] = []
    try:
        a = json.loads(analysis_path.read_text(encoding="utf-8"))
    except Exception as e:
        return [f"JSON 파싱 실패: {e}"]

    expected: list[str] = []
    m: dict = {}
    holding: dict[str, bool] = {}
    if market_path and market_path.exists():
        m = json.loads(market_path.read_text(encoding="utf-8"))
        expected = [t["symbol"] for t in m.get("tickers", [])]
        holding = {t["symbol"]: bool(t.get("holding")) for t in m.get("tickers", []) if "holding" in t}

    tk = a.get("tickers")
    if not isinstance(tk, dict):
        errs.append("'tickers' 객체가 없음")
        tk = {}
    for sym in expected:
        if sym not in tk:
            errs.append(f"tickers.{sym} 누락")
    for sym, t in tk.items():
        p = f"tickers.{sym}"
        if not isinstance(t.get("headline"), str) or not t["headline"].strip():
            errs.append(f"{p}.headline 비어있음")
        mr = t.get("move_reasons")
        if not isinstance(mr, list) or not (1 <= len(mr) <= 4):
            errs.append(f"{p}.move_reasons 는 1~4개 리스트")
        wo = t.get("weekly_outlook")
        if not isinstance(wo, dict) or not wo.get("summary"):
            errs.append(f"{p}.weekly_outlook.summary 비어있음")
        elif wo.get("stance") not in STANCES:
            errs.append(f"{p}.weekly_outlook.stance 는 {STANCES} 중 하나")
        q = (m.get("quotes") or {}).get(sym) or {}
        av = (m.get("analyst") or {}).get(sym) or {}
        tg = [v for v in (av.get("target_mean"), av.get("target_median")) if v] if m else None
        errs += _check_moat(p, t.get("moat_watch"))
        errs += _check_plan(p, t.get("action_plan"), holding.get(sym), _anchor_prices(m, sym), q.get("close"), tg)
        for i, x in enumerate(t.get("extra_actions") or []):
            if not isinstance(x, dict) or not x.get("firm"):
                errs.append(f"{p}.extra_actions[{i}].firm 비어있음")

    n = a.get("news")
    if not isinstance(n, dict):
        errs.append("'news' 객체가 없음")
    else:
        top = n.get("top_news")
        if not isinstance(top, list) or not (3 <= len(top) <= 5):
            errs.append("news.top_news 는 3~5개")
        else:
            for i, x in enumerate(top):
                if not x.get("title") or not x.get("summary"):
                    errs.append(f"news.top_news[{i}] title/summary 비어있음")
                if x.get("impact") not in IMPACTS:
                    errs.append(f"news.top_news[{i}].impact 는 {IMPACTS} 중 하나")
        if not n.get("market_wrap"):
            errs.append("news.market_wrap 비어있음")

    ss = a.get("strategy_summary")
    if not isinstance(ss, dict) or not ss.get("overview"):
        errs.append("strategy_summary.overview 비어있음")

    meta = a.get("meta") or {}
    if meta.get("mode") not in (None, "daily", "weekly"):
        errs.append("meta.mode 는 daily 또는 weekly")
    if meta.get("mode") == "weekly":
        wa = a.get("week_ahead")
        if not isinstance(wa, dict):
            errs.append("주간 모드: 'week_ahead' 객체가 없음")
        else:
            cal = wa.get("calendar")
            if not isinstance(cal, list) or not cal:
                errs.append("week_ahead.calendar 는 1개 이상")
            for i, e in enumerate(cal or []):
                if not e.get("date") or not e.get("event"):
                    errs.append(f"week_ahead.calendar[{i}] date/event 비어있음")
            for i, e in enumerate(wa.get("earnings") or []):
                if not e.get("date") or not e.get("ticker"):
                    errs.append(f"week_ahead.earnings[{i}] date/ticker 비어있음")
    return errs


if __name__ == "__main__":  # python -m briefing.validate data/2026-10-16  (표준 라이브러리만 사용)
    import sys

    d = Path(sys.argv[1])
    problems = validate(d / "analysis.json", d / "market.json")
    if problems:
        print("❌ 검사 실패:")
        for e in problems:
            print("  -", e)
        sys.exit(1)
    print("✅ analysis.json 검사 통과")
