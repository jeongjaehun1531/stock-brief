"""미국 거래일 판정.

한국시간 평일 아침(08:00 무렵)은 미국 동부시간 '전날 저녁'이므로,
'가장 최근에 마감된 NYSE 세션'이 브리핑 대상 거래일이 된다.

  KST 월 08:50 → 미국 금 종가
  KST 화 08:50 → 미국 월 종가   …   KST 금 08:50 → 미국 목 종가
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")


@dataclass
class SessionInfo:
    session: date          # 브리핑 대상 거래일 (미국 날짜)
    closed_yesterday: bool  # 미국 '전일'이 평일인데 휴장이었는지
    note: str = ""


def last_completed_session(now: datetime | None = None) -> SessionInfo:
    now = (now or datetime.now(tz=ET)).astimezone(ET)
    try:
        import exchange_calendars as xcals
        import pandas as pd

        cal = xcals.get_calendar("XNYS")
        start = (now - timedelta(days=14)).date()
        sched = cal.schedule.loc[str(start): str(now.date())]
        ts_now = pd.Timestamp(now).tz_convert("UTC")
        done = sched[sched["close"] <= ts_now]
        session = done.index[-1].date()
        today_et = now.date()
        holiday = today_et.weekday() < 5 and not cal.is_session(str(today_et)) and now.hour >= 16
        note = "전일 미국 증시 휴장 → 직전 거래일 종가 기준" if holiday else ""
        return SessionInfo(session=session, closed_yesterday=holiday, note=note)
    except Exception as e:  # 캘린더 라이브러리 문제 시: 평일 단순 계산 (휴일 미반영)
        log.warning("exchange_calendars 사용 실패, 단순 계산으로 대체: %s", e)
        d = now.date() if now.hour >= 16 else now.date() - timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        return SessionInfo(session=d, closed_yesterday=False)
