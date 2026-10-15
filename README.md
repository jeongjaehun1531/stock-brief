# 🇺🇸 미국주식 모닝 브리핑 (stock-brief)

매일 아침 **08:50 KST**에 **텔레그램 카드 앨범**으로 받습니다.
- **화~토**: 전일 미국장 종가 브리핑 (등락 이유·주간 전망·증권사 목표가·Top 5 뉴스)
- **월**: 주간 프리뷰 (주말 이슈·이번 주 경제지표/실적 일정·지난주 성적표·종목별 이번 주 전망)
API 크레딧 없이 **GitHub Actions(무료) + Claude 예약 작업(구독)** 조합으로 동작합니다.

## 동작 흐름

| 시각(KST) | 어디서 | 무엇을 | 결과 |
|---|---|---|---|
| 07:10 | GitHub Actions `1) Collect` | yfinance로 종가·등락률·지수·목표가·증권사 액션 수집 | `data/<날짜>/market.json` |
| 08:05 | Claude 예약 작업 | `ANALYST.md` 지침대로 웹검색 분석 (Sonnet) | `data/<날짜>/analysis.json` |
| 08:25~08:50 | GitHub Actions `2) Render & send` | analysis 대기 → 카드 렌더 → **08:50 텔레그램 전송** | 카드 앨범 + HTML 리포트 |

- **숫자는 yfinance**(정확), **해석은 Claude**(등락 이유·주간 전망·증권사 의견 요약·Top 5 뉴스)
- Claude 분석이 08:48까지 없으면 시세·목표가만 담아 전송 (브리핑은 항상 도착)
- 수집 단계가 실패해도 전송 단계에서 직접 다시 수집

## md 파일로 제어 (코드 수정 불필요)

| 파일 | 바꾸는 것 |
|---|---|
| `tickers.md` | 관심종목 추가/제거 — `- NVDA \| 엔비디아 \| 메모`, 줄 앞 `#` = 제외 |
| `ANALYST.md` | Claude 분석 방식·분량·말투·검색 횟수·출력 형식 |
| `config.yaml` | 전송 시각, 주간 프리뷰 요일, 표시 지표, '주요 증권사' 목록, PPT 첨부 여부 |

GitHub 앱/웹에서 편집 → 커밋하면 다음날 아침부터 반영.

## 최초 설정 (1회)

1. **텔레그램 봇**: `@BotFather` → `/newbot` → 토큰 복사. 봇에게 아무 메시지를 보낸 뒤
   `https://api.telegram.org/bot<토큰>/getUpdates` 에서 `"chat":{"id": …}` 숫자 확인
2. 저장소 **Settings → Secrets and variables → Actions → New repository secret**
   - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
3. **Actions** 탭 → `2) Render & send briefing` → **Run workflow** → `mock` 선택 → 텔레그램 수신 확인

## 수동 실행 (Actions 탭)

- `1) Collect market data` → Run : 오늘 시세 수집
- `2) Render & send briefing` → `now` : 지금 있는 데이터로 즉시 전송 / `mock` : 샘플 전송

## 로컬 실행

```bash
pip install -r requirements.txt && python -m playwright install chromium
python main.py mock                       # 샘플 카드 → output/mock/cards
python main.py collect                    # 시세 수집
python main.py render --day 2026-10-16    # 카드만 생성
python main.py deliver --no-wait          # 즉시 전송 (.env 필요)
python main.py api                        # (선택) Claude API 크레딧으로 단독 실행
```

## 구조

```
tickers.md / ANALYST.md / config.yaml   ← 제어 파일
main.py                                  collect | deliver | render | mock | build-web-market | api
briefing/  market_data.py analyst.py market_calendar.py   수집 (yfinance, NYSE 휴장 반영)
           store.py validate.py web_market.py             단계 간 JSON / 검사 / 비상 수집
           report.py render.py pptx_export.py             HTML → 카드 PNG → (PPTX)
           delivery/telegram.py email.py                  전송
           ai_analyst.py                                  (선택) API 모드
templates/report.html.j2                                  카드 디자인 (상승 빨강 / 하락 파랑)
data/<날짜>/  market.json analysis.json sent.txt          매일 기록
.github/workflows/  collect.yml deliver.yml
```

⚠️ 정보 제공용이며 투자 권유가 아닙니다.
