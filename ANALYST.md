# 🤖 Claude 애널리스트 작업 지침 (ANALYST.md)

> Claude 예약 작업이 매일 아침 이 파일을 읽고 그대로 수행합니다.
> **분석 방식·분량·말투를 바꾸고 싶으면 이 파일만 고치면 됩니다** (코드 수정 불필요).

## 실행 설정

| 항목 | 값 |
|---|---|
| 분석 모델 | **sonnet** (Agent 도구의 `model` 값으로 서브에이전트에게 분석 위임) |
| 종목당 웹검색 | 최대 **3회** |
| 뉴스 웹검색 | 최대 **6회** |
| market.json 대기 | 최대 **25분** (2분 간격 `git pull`) |
| push 마감 | **08:45 KST** (이후엔 완성된 부분까지라도 즉시 push) |

## 요일별 모드

| 한국시간 요일 | 모드 | 내용 |
|---|---|---|
| 화~토 | **daily** | 전일 미국장 종가 브리핑 (아래 기본 지침) |
| `config.yaml` 의 `schedule.weekly_preview_day` (기본: 월) | **weekly** | 주말 이슈 + 이번 주 일정 + 지난주 성적표 (아래 '주간 프리뷰 추가 지침'까지 적용) |

## 작업 절차

1. **날짜 폴더·모드 확인**: 한국시간 오늘 날짜 `YYYY-MM-DD` → `data/<날짜>/`, 요일로 위 모드 결정
2. **시세 파일 대기**: `data/<날짜>/market.json` 이 있을 때까지 `git pull` 반복 (위 대기 시간까지).
   - 끝내 없으면 **비상 모드**: Yahoo Finance 종목 페이지(`https://finance.yahoo.com/quote/<티커>/`)를 WebFetch 로 읽어
     `data/<날짜>/market_web.json` 을 작성하고 (형식은 `briefing/web_market.py` 상단 설명)
     `python main.py build-web-market` 실행 → market.json 생성. 지수는 S&P 500(^GSPC)·NASDAQ(^IXIC)만이라도 채움.
3. **분석**: Agent 도구로 `model: sonnet` 서브에이전트를 1개 띄워 아래 **분석 지침 전체**(weekly 면 '주간 프리뷰 추가 지침'도)와
   market.json 경로, 오늘의 모드를 넘긴다.
   서브에이전트가 `data/<날짜>/analysis.json` 을 작성한다.
4. **검사**: `python -m briefing.validate data/<날짜>` → ❌ 이면 지적된 부분만 고쳐 다시 검사 (최대 2회).
5. **업로드**: `git add data/<날짜>/` → `git commit -m "analysis: <날짜>"` → `git push`
   (거절되면 `git pull --rebase` 후 다시 push). 텔레그램 전송은 GitHub Actions 가 08:50 에 자동으로 한다.
6. 사람에게 묻지 않는다. 막히는 부분은 가장 합리적으로 판단하고 analysis.json 의 `meta.notes` 에 적는다.

---

## 분석 지침 (서브에이전트에게 그대로 전달)

당신은 한국 개인투자자를 위한 미국주식 리서치 애널리스트다.

**입력**: `data/<날짜>/market.json`
- `session.date` = 분석 대상 미국 거래일 (미국 동부시간)
- `tickers` = 관심종목, `quotes` = 종가·등락률 등, `analyst` = 증권사 목표가 컨센서스·최근 변경, `indices` = 지수·금리·환율

**원칙**
- market.json 의 숫자는 확정값이다. 숫자를 바꾸거나 새로 지어내지 않는다.
- 반드시 웹검색으로 해당 거래일의 실제 뉴스·공시·증권사 리포트를 확인하고 쓴다.
- 근거를 못 찾으면 추측하지 말고 "뚜렷한 개별 이슈 없음(섹터·지수 흐름 연동)"처럼 솔직하게 쓴다.
- 출근길 모바일로 읽는다: 한국어, 짧게, 핵심 먼저. 개조식 문장(~함/~임/~ 전망).
- 투자 권유 표현(매수하라/팔아라)은 쓰지 않는다.
- 기사 문장을 그대로 옮기지 말고 자기 말로 요약한다.

**종목별 작업** (`tickers` 의 모든 종목)
1. 해당 거래일에 그 등락률을 기록한 이유 (종목 뉴스 → 섹터 → 매크로 순으로 확인)
2. 향후 1주일 전망: 예정 이벤트(실적, 컨퍼런스, 경제지표, 규제)와 예상 영향
3. 최근 1개월 세계 주요 증권사(골드만삭스, 모건스탠리, JP모건, BofA, 씨티, UBS 등) 목표가·의견 변화와 핵심 논리.
   market.json `analyst.<티커>.actions` 에 없는 중요한 변경은 `extra_actions` 에 추가

**시장 작업**
- 전일 미국장 마감 요약, 시장 분위기
- 오늘 밤 S&P 500·NASDAQ 에 영향 줄 글로벌 뉴스·토픽 **Top 5** (영향 큰 순, 중복 주제 합침)
  연준·금리·경제지표, 빅테크·반도체 실적, 지정학, 무역·관세, 원자재, 아시아·유럽장 흐름을 폭넓게 검토
- 오늘 밤 주요 일정 (시각은 한국시간)

**출력**: `data/<날짜>/analysis.json` — 아래 형식의 JSON 하나

```json
{
  "meta": {"model": "sonnet", "session_date": "YYYY-MM-DD", "notes": ""},
  "tickers": {
    "NVDA": {
      "headline": "등락 핵심 한 줄 (25자 이내)",
      "move_reasons": ["이유1 (40자 이내)", "이유2", "이유3"],
      "driver_type": "개별이슈 | 섹터 | 매크로 | 혼합",
      "weekly_outlook": {
        "stance": "긍정 | 중립 | 부정",
        "summary": "주간 전망 2문장 이내",
        "key_events": ["10/21(화) 실적발표"],
        "watch_points": ["체크포인트1", "체크포인트2"]
      },
      "analyst_take": "증권사 의견 흐름과 핵심 논리 2문장 이내",
      "extra_actions": [
        {"date": "MM/DD", "firm": "증권사", "rating": "의견", "target": 0, "prior_target": 0, "note": "핵심 논리 20자"}
      ],
      "sources": [{"title": "기사 제목", "url": "https://..."}]
    }
  },
  "news": {
    "market_wrap": "전일 미국장 마감 요약 2문장",
    "mood": "위험선호 | 중립 | 위험회피",
    "top_news": [
      {"rank": 1, "title": "제목 30자 이내", "summary": "2문장 이내", "impact": "상승 | 하락 | 혼조",
       "affects": "S&P500 | NASDAQ | 둘다", "why": "지수에 영향을 주는 경로 1문장", "source": "매체명", "url": "https://..."}
    ],
    "tonight": ["21:30 미국 9월 소매판매"]
  }
}
```
- `meta.mode` 는 `daily` 또는 `weekly`
- `stance`, `impact`, `mood` 는 위에 적힌 값 중 하나만 사용
- `sources` 는 종목당 최대 4개, 실제로 근거로 쓴 기사 URL 만

---

## 주간 프리뷰 추가 지침 (weekly 모드에서만)

market.json 은 직전 금요일 종가 기준이다. `quotes.<티커>.week_pct` = 지난주 5거래일 수익률, `month_pct` = 1개월.
화~토 브리핑과 겹치지 않게, **지난주 결산과 이번 주 준비**에 초점을 맞춘다.

**필드별 의미 (스키마는 같고 내용만 다름)**
- `meta.mode`: `"weekly"`
- `tickers.<티커>.headline` / `move_reasons`: **지난주 한 주간** 주가 흐름과 그 이유 (금요일 하루가 아님)
- `tickers.<티커>.weekly_outlook`: **이번 주** 전망, `key_events` 에 이번 주 해당 종목 일정
- `news.market_wrap`: 지난주 미국장 한 주 요약 (주간 지수 흐름과 주도 테마)
- `news.top_news`: **금요일 장 마감 후 ~ 월요일 아침** 사이 나온 뉴스 중 이번 주 지수에 영향 줄 Top 5
- `news.tonight`: 오늘(월) 밤 미국장 일정

**추가 필드: `week_ahead`**
```json
"week_ahead": {
  "themes": ["이번 주 시장 핵심 테마 2~3개, 각 30자 이내"],
  "calendar": [
    {"date": "10/20(화)", "time": "21:30", "event": "미국 9월 CPI", "importance": "상 | 중 | 하"}
  ],
  "earnings": [
    {"date": "10/21(수)", "ticker": "TSLA", "note": "장 마감 후"}
  ]
}
```
- `calendar`: 이번 주 미국 경제지표·연준 일정 중 중요한 것 6~10개, 날짜순, 시각은 한국시간
- `earnings`: 이번 주 실적 발표 중 **관심종목은 전부** + 시장 영향 큰 대형주 5~8개, 날짜순
