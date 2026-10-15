"""analysis.json 형식 검사. Claude 예약 작업이 push 전에 반드시 실행."""
from __future__ import annotations

import json
from pathlib import Path

STANCES = {"긍정", "중립", "부정"}
IMPACTS = {"상승", "하락", "혼조"}


def validate(analysis_path: Path, market_path: Path | None = None) -> list[str]:
    errs: list[str] = []
    try:
        a = json.loads(analysis_path.read_text(encoding="utf-8"))
    except Exception as e:
        return [f"JSON 파싱 실패: {e}"]

    expected: list[str] = []
    if market_path and market_path.exists():
        m = json.loads(market_path.read_text(encoding="utf-8"))
        expected = [t["symbol"] for t in m.get("tickers", [])]

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
