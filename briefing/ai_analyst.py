"""Claude API + 웹검색으로 정성 분석 생성.

  1) 종목별: 당일 등락 사유, 주간 전망, 증권사 의견 요약
  2) 시장: S&P500·NASDAQ 에 영향 줄 Top 5 글로벌 뉴스/토픽

숫자(종가·등락률·목표가)는 yfinance 값을 프롬프트로 넘겨 '사실'로 고정하고,
Claude 는 그 숫자를 설명하는 이유·전망만 웹검색 근거로 작성하게 한다.
"""
from __future__ import annotations

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from .analyst import AnalystView
from .config import Ticker
from .market_data import Quote

log = logging.getLogger(__name__)

SYSTEM = """당신은 한국 개인투자자를 위한 미국주식 리서치 애널리스트입니다.
- 반드시 웹검색으로 해당 거래일의 실제 뉴스·공시·증권사 리포트를 확인한 뒤 작성합니다.
- 제공된 시세 숫자는 확정값입니다. 숫자를 바꾸거나 새로 지어내지 마세요.
- 근거를 찾지 못한 내용은 추측하지 말고 "뚜렷한 개별 이슈 없음(섹터/지수 흐름 연동)"처럼 솔직하게 씁니다.
- 출근길 모바일로 읽습니다: 한국어, 짧은 문장, 핵심 먼저. 문장 끝은 '~함/~임/~ 전망' 같은 개조식.
- 투자 권유가 아닌 정보 제공 목적입니다. 매수/매도 지시 표현은 쓰지 않습니다.
- 최종 답변은 지정된 JSON 하나만 출력합니다(설명·마크다운 금지)."""


def _fmt(x, nd=2):
    return "N/A" if x is None else f"{x:,.{nd}f}"


def _ticker_prompt(t: Ticker, q: Quote, av: AnalystView, session: date) -> str:
    actions = "\n".join(
        f"  - {a.date} {a.firm}: {a.from_rating}→{a.rating}, 목표가 {_fmt(a.prior_target)}→{_fmt(a.target)}"
        for a in av.actions
    ) or "  - (최근 데이터 없음)"
    return f"""대상 거래일(미국 동부시간): {session:%Y-%m-%d}
종목: {t.symbol} ({t.label}) {('메모: ' + t.memo) if t.memo else ''}

[확정 시세]
종가 ${_fmt(q.close)} / 전일대비 {_fmt(q.change_pct)}% / 5거래일 {_fmt(q.week_pct)}% / 1개월 {_fmt(q.month_pct)}%
52주 범위 ${_fmt(q.low_52w)} ~ ${_fmt(q.high_52w)} / 거래량 20일평균 대비 {_fmt(q.volume_ratio)}배
다음 실적발표(추정): {q.next_earnings or '미확인'}

[증권사 컨센서스(yfinance)]
평균 목표가 ${_fmt(av.target_mean)} (최고 {_fmt(av.target_high)} / 최저 {_fmt(av.target_low)}), 매수 {av.buy} · 보유 {av.hold} · 매도 {av.sell}
최근 목표가 변경:
{actions}

[작업]
1. {session:%Y-%m-%d} 장에서 {t.symbol} 가 위 등락률을 기록한 이유를 웹검색으로 확인 (종목 뉴스, 섹터·지수 흐름, 매크로).
2. 다가오는 1주일 전망: 예정 이벤트(실적, 컨퍼런스, 경제지표, 규제 등)와 주가에 미칠 영향.
3. 최근 1개월 내 세계 주요 증권사(골드만삭스, 모건스탠리, JP모건, BofA, 씨티 등) 목표가·의견 변화를 확인하고,
   위 목록에 없는 중요한 액션이 있으면 extra_actions 에 추가. 왜 올리거나 내렸는지 핵심 논리를 요약.

[출력 JSON 스키마]
{{
  "headline": "등락 핵심을 담은 25자 이내 한 줄",
  "move_reasons": ["이유1 (40자 이내)", "이유2", "이유3"],
  "driver_type": "개별이슈 | 섹터 | 매크로 | 혼합",
  "weekly_outlook": {{
    "stance": "긍정 | 중립 | 부정",
    "summary": "주간 전망 2문장 이내",
    "key_events": ["10/21(화) 실적발표", "..."],
    "watch_points": ["체크포인트 1", "체크포인트 2"]
  }},
  "analyst_take": "증권사 의견 흐름과 핵심 논리 2문장 이내",
  "extra_actions": [
    {{"date": "MM/DD", "firm": "증권사", "rating": "의견", "target": 0, "prior_target": 0, "note": "핵심 논리 20자"}}
  ],
  "sources": [{{"title": "기사 제목", "url": "https://..."}}]
}}"""


def _news_prompt(session: date, index_lines: str) -> str:
    return f"""대상: {session:%Y-%m-%d} 미국 장 마감 후 ~ 한국시간 다음날 아침까지의 글로벌 뉴스.

[확정 지표]
{index_lines}

[작업]
오늘 밤 미국장(S&P 500, NASDAQ)에 영향을 줄 수 있는 글로벌 뉴스·토픽 Top 5 를 웹검색으로 선정.
- 연준/금리/경제지표, 빅테크·반도체 실적, 지정학, 무역·관세, 원자재, 아시아·유럽장 흐름 등을 폭넓게 검토
- 영향도가 큰 순서. 중복 주제는 하나로 합침.
- 전일 장 마감 요약과 오늘 밤 주요 일정(경제지표 발표 시각은 한국시간으로)도 작성.

[출력 JSON 스키마]
{{
  "market_wrap": "전일 미국장 마감 요약 2문장 (지수 움직임의 원인 중심)",
  "mood": "위험선호 | 중립 | 위험회피",
  "top_news": [
    {{
      "rank": 1,
      "title": "한국어 제목 30자 이내",
      "summary": "핵심 내용 2문장 이내",
      "impact": "상승 | 하락 | 혼조",
      "affects": "S&P500 | NASDAQ | 둘다",
      "why": "지수에 영향을 주는 경로 1문장",
      "source": "매체명",
      "url": "https://..."
    }}
  ],
  "tonight": ["22:30 미국 9월 소매판매", "장 마감 후 넷플릭스 실적"]
}}"""


def _extract_json(text: str) -> dict:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("JSON 을 찾지 못함")
    return json.loads(text[start: end + 1])


class ClaudeAnalyst:
    def __init__(self, cfg: dict):
        import anthropic

        self.client = anthropic.Anthropic()
        c = cfg.get("claude", {})
        self.model = c.get("model", "claude-sonnet-5-5")
        self.tool_type = c.get("web_search_tool", "web_search_20260318")
        self.max_searches_ticker = int(c.get("max_searches_per_ticker", 4))
        self.max_searches_news = int(c.get("max_searches_news", 6))
        self.workers = int(c.get("parallel_workers", 3))
        self.retries = int(c.get("max_retries", 2))
        self.usage = {"input_tokens": 0, "output_tokens": 0, "web_searches": 0}

    # ── low level ──────────────────────────────────────────
    def _tool(self, max_uses: int) -> dict:
        tool = {"type": self.tool_type, "name": "web_search", "max_uses": max_uses}
        if self.tool_type >= "web_search_20260318":
            tool["response_inclusion"] = "excluded"   # 검색 원문을 응답에서 빼 토큰 절약
        return tool

    def _ask(self, prompt: str, max_uses: int) -> tuple[dict, list[dict]]:
        messages = [{"role": "user", "content": prompt}]
        last_err = None
        for attempt in range(self.retries + 1):
            try:
                content_all = []
                for _ in range(5):  # pause_turn 이어받기
                    resp = self.client.messages.create(
                        model=self.model,
                        max_tokens=4000,
                        system=SYSTEM,
                        tools=[self._tool(max_uses)],
                        messages=messages,
                    )
                    self._track(resp.usage)
                    content_all.extend(resp.content)
                    if resp.stop_reason != "pause_turn":
                        break
                    messages = messages + [{
                        "role": "assistant",
                        "content": [b.model_dump(exclude_none=True) for b in resp.content],
                    }]
                texts, cites = [], []
                for b in content_all:
                    if getattr(b, "type", "") == "text":
                        texts.append(b.text)
                        for c in getattr(b, "citations", None) or []:
                            url = getattr(c, "url", None)
                            if url:
                                cites.append({"title": getattr(c, "title", "") or url, "url": url})
                # 최종 답은 마지막 텍스트들. 뒤에서부터 늘려가며 JSON 이 되는 지점을 찾음
                data = None
                for i in range(len(texts) - 1, -1, -1):
                    try:
                        data = _extract_json("".join(texts[i:]))
                        break
                    except Exception:
                        continue
                if data is None:
                    raise ValueError("응답에서 JSON 파싱 실패")
                return data, cites
            except Exception as e:
                last_err = e
                log.warning("Claude 호출 실패(%d/%d): %s", attempt + 1, self.retries + 1, e)
                time.sleep(5 * (attempt + 1))
                messages = [{"role": "user", "content": prompt + "\n\n반드시 JSON 하나만 출력하세요."}]
        raise RuntimeError(f"Claude 분석 실패: {last_err}")

    def _track(self, usage) -> None:
        self.usage["input_tokens"] += getattr(usage, "input_tokens", 0) or 0
        self.usage["output_tokens"] += getattr(usage, "output_tokens", 0) or 0
        stu = getattr(usage, "server_tool_use", None)
        if stu is not None:
            self.usage["web_searches"] += getattr(stu, "web_search_requests", 0) or 0

    # ── public ─────────────────────────────────────────────
    def analyze_ticker(self, t: Ticker, q: Quote, av: AnalystView, session: date) -> dict:
        try:
            data, cites = self._ask(_ticker_prompt(t, q, av, session), self.max_searches_ticker)
            data["sources"] = _merge_sources(data.get("sources", []), cites)
            return data
        except Exception as e:
            log.error("%s 분석 실패: %s", t.symbol, e)
            return {"headline": "분석 생성 실패", "move_reasons": [str(e)[:80]], "error": True}

    def analyze_tickers(self, items, session: date) -> dict[str, dict]:
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            futs = {t.symbol: ex.submit(self.analyze_ticker, t, q, av, session) for t, q, av in items}
            return {s: f.result() for s, f in futs.items()}

    def top_news(self, session: date, indices: dict[str, Quote]) -> dict:
        lines = "\n".join(
            f"- {q.name}: {_fmt(q.close)} ({_fmt(q.change_pct)}%)" for q in indices.values() if q.close
        )
        try:
            data, cites = self._ask(_news_prompt(session, lines), self.max_searches_news)
            data["top_news"] = (data.get("top_news") or [])[:5]
            return data
        except Exception as e:
            log.error("뉴스 분석 실패: %s", e)
            return {"market_wrap": "뉴스 분석 생성 실패", "top_news": [], "tonight": [], "error": True}

    def estimated_cost_usd(self) -> float:
        # Sonnet 5.5 기준 단가 ($/MTok): 입력 2, 출력 10, 검색 $10/1000회
        price = {"claude-sonnet-5-5": (2, 10), "claude-haiku-5-5": (0.1, 0.5), "claude-opus-5-5": (4, 20)}
        pin, pout = price.get(self.model, (2, 10))
        u = self.usage
        return u["input_tokens"] / 1e6 * pin + u["output_tokens"] / 1e6 * pout + u["web_searches"] * 0.01


def _merge_sources(declared: list, cited: list, limit: int = 4) -> list[dict]:
    seen, out = set(), []
    for s in list(cited) + list(declared or []):
        url = (s or {}).get("url")
        if url and url.startswith("http") and url not in seen:
            seen.add(url)
            out.append({"title": (s.get("title") or url)[:80], "url": url})
    return out[:limit]
