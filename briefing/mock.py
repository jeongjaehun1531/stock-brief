"""API 키 없이 디자인·파이프라인을 확인하기 위한 샘플 데이터 (--mock).
숫자와 뉴스는 모두 가상의 예시입니다."""
from __future__ import annotations

import math
import random
from datetime import date

from .analyst import AnalystAction, AnalystView
from .config import Ticker
from .market_data import Quote


def _series(seed: int, base: float, drift: float) -> list[float]:
    rnd = random.Random(seed)
    v, out = base, []
    for i in range(30):
        v *= 1 + drift / 30 + rnd.uniform(-0.018, 0.018) + 0.004 * math.sin(i / 3)
        out.append(round(v, 2))
    return out


def mock_quotes(tickers: list[Ticker], session: date) -> dict[str, Quote]:
    out = {}
    for i, t in enumerate(tickers):
        s = _series(i + 7, 100 + 40 * i, (-1) ** i * 0.06)
        q = Quote(symbol=t.symbol, name=t.label, as_of=session, spark=s)
        q.close, q.prev_close = s[-1], s[-2]
        q.change = q.close - q.prev_close
        q.change_pct = (q.close / q.prev_close - 1) * 100
        q.week_pct = (q.close / s[-6] - 1) * 100
        q.month_pct = (q.close / s[0] - 1) * 100
        q.ytd_pct = q.month_pct * 2.3
        q.high_52w, q.low_52w = max(s) * 1.15, min(s) * 0.8
        q.volume_ratio = 0.8 + 0.25 * i
        q.market_cap = (3.1 - 0.5 * i) * 1e12 if i < 5 else 9e10
        q.next_earnings = "2026-10-29" if i % 2 == 0 else None
        out[t.symbol] = q
    return out


def mock_indices(symbols: dict[str, str]) -> dict[str, Quote]:
    vals = {"^GSPC": (6812.4, 0.62), "^IXIC": (23104.9, 0.94), "^DJI": (46210.3, 0.21),
            "^SOX": (6890.2, 1.85), "^VIX": (16.4, -4.1), "^TNX": (4.08, -0.7),
            "DX-Y.NYB": (98.7, -0.2), "KRW=X": (1392.5, 0.15), "CL=F": (61.3, -1.2),
            "ES=F": (6830.0, 0.12), "NQ=F": (25480.0, 0.18)}
    out = {}
    for s, name in symbols.items():
        c, p = vals.get(s, (100.0, 0.0))
        q = Quote(symbol=s, name=name, close=c, change_pct=p, change=c * p / 100)
        out[s] = q
    return out


def mock_views(tickers: list[Ticker], quotes: dict[str, Quote]) -> dict[str, AnalystView]:
    firms = ["Goldman Sachs", "Morgan Stanley", "JP Morgan", "Bank of America", "UBS", "Citigroup"]
    out = {}
    for i, t in enumerate(tickers):
        px = quotes[t.symbol].close
        v = AnalystView(symbol=t.symbol, target_mean=px * (1.12 - 0.04 * i), target_median=px * 1.1,
                        target_high=px * 1.45, target_low=px * 0.78, buy=38 - 5 * i, hold=6 + 2 * i, sell=1 + i % 3)
        v.n_analysts = v.buy + v.hold + v.sell
        for k in range(3):
            tgt = round(px * (1.15 + 0.05 * k) / 5) * 5
            v.actions.append(AnalystAction(
                date=f"10/{14 - 3 * k:02d}", firm=firms[(i + k) % len(firms)],
                action="up" if k != 1 else "main", rating=["Buy", "Overweight", "Outperform"][k],
                from_rating="Neutral" if k == 2 else "", target=tgt,
                prior_target=tgt - 15 if k != 1 else tgt,
            ))
        out[t.symbol] = v
    return out


def mock_ai_tickers(tickers: list[Ticker], quotes: dict[str, Quote]) -> dict[str, dict]:
    out = {}
    for i, t in enumerate(tickers):
        up = (quotes[t.symbol].change_pct or 0) >= 0
        out[t.symbol] = {
            "headline": ("[예시] 데이터센터 수요 기대에 강세" if up else "[예시] 차익실현 매물에 약세"),
            "move_reasons": [
                "[예시] 경쟁사 실적 호조로 섹터 전반 투자심리 개선" if up else "[예시] 단기 급등 후 차익실현 매물 출회",
                "[예시] 주요 고객사의 설비투자(Capex) 상향 발표",
                "[예시] 나스닥 지수 상승과 동반한 대형 기술주 강세",
            ],
            "driver_type": "혼합",
            "weekly_outlook": {
                "stance": "긍정" if i % 3 == 0 else ("중립" if i % 3 == 1 else "부정"),
                "summary": "[예시] 다음 주 실적 발표 전까지 기대감이 주가를 지지할 전망. 다만 금리 변동성 확대 시 밸류에이션 부담 부각 가능.",
                "key_events": ["10/21(화) 9월 CPI", "10/29(수) 실적발표"],
                "watch_points": ["가이던스 상향 여부", "10년물 금리 4.2% 돌파 여부"],
            },
            "analyst_take": "[예시] 주요 IB 다수가 AI 인프라 수요 지속을 근거로 목표가를 상향. 일부는 밸류에이션 부담으로 의견 유지.",
            "extra_actions": [],
            "sources": [{"title": "[예시] 샘플 기사 제목", "url": "https://example.com"}],
        }
    return out


def mock_news() -> dict:
    return {
        "market_wrap": "[예시] 반도체주 강세 속 나스닥이 1% 가까이 상승. 국채금리 하락이 성장주에 우호적으로 작용함.",
        "mood": "위험선호",
        "top_news": [
            {"title": "[예시] 연준 인사 '추가 인하 여지' 발언", "summary": "연준 이사가 고용 둔화를 근거로 연내 추가 인하 가능성을 언급함.",
             "impact": "상승", "affects": "둘다", "why": "금리 인하 기대 → 성장주 밸류에이션 부담 완화", "source": "Reuters", "url": "https://example.com"},
            {"title": "[예시] TSMC 3분기 실적 서프라이즈", "summary": "AI 가속기 수요로 매출 가이던스를 상향 조정함.",
             "impact": "상승", "affects": "NASDAQ", "why": "반도체 공급망 전반의 실적 기대 상향", "source": "Bloomberg", "url": "https://example.com"},
            {"title": "[예시] 미·중 무역협상 일정 연기", "summary": "고위급 회담이 다음 달로 미뤄지며 관세 불확실성이 이어짐.",
             "impact": "하락", "affects": "둘다", "why": "공급망·수출주 실적 불확실성 확대", "source": "WSJ", "url": "https://example.com"},
            {"title": "[예시] 국제유가 2주 최저", "summary": "OPEC+ 증산 전망에 WTI가 배럴당 61달러대로 하락함.",
             "impact": "혼조", "affects": "S&P500", "why": "인플레 부담 완화 vs 에너지 섹터 약세", "source": "CNBC", "url": "https://example.com"},
            {"title": "[예시] 넷플릭스 장 마감 후 실적", "summary": "구독자 대신 광고 매출 성장률이 핵심 지표로 주목받음.",
             "impact": "혼조", "affects": "NASDAQ", "why": "빅테크 실적 시즌 분위기를 가늠할 첫 시험대", "source": "MarketWatch", "url": "https://example.com"},
        ],
        "tonight": ["21:30 미국 9월 소매판매", "23:00 파월 의장 연설", "장 마감 후 넷플릭스 실적"],
    }
