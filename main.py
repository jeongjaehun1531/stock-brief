"""미국주식 데일리 브리핑 — 엔트리포인트.

평일 흐름 (한국시간)
  07:10  python main.py collect     GitHub Actions: yfinance → data/<날짜>/market.json 커밋
  08:05  (Claude 예약 작업)          ANALYST.md 지침대로 분석 → data/<날짜>/analysis.json 커밋
  08:25  python main.py deliver     GitHub Actions: analysis 대기 → 카드 렌더 → 08:50 텔레그램 전송

기타
  python main.py mock               샘플 데이터로 카드 디자인 확인 (전송 안 함)
  python main.py render --day 2026-10-16   해당 날짜 데이터로 카드만 생성 (전송 안 함)
  python main.py build-web-market   비상용: market_web.json → market.json
  python main.py api                Claude API(크레딧) 로 한 번에 실행하는 단독 모드
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from briefing.config import ROOT, load_config, load_tickers
from briefing.market_calendar import last_completed_session
from briefing.report import build_context, render_html, save_html
from briefing.store import day_dir, load_analysis, load_market, save_market, today_kst

log = logging.getLogger("briefing")


# ── 수집 ──────────────────────────────────────────────────
def collect_market(cfg) -> dict:
    from briefing.analyst import fetch_analyst_view
    from briefing.market_data import enrich_stock_info, fetch_quotes

    tickers = load_tickers(cfg)
    sess = last_completed_session()
    log.info("관심종목 %s / 대상 거래일 %s %s", [t.symbol for t in tickers], sess.session, sess.note)
    mcfg = cfg.get("market", {})
    quotes = fetch_quotes({t.symbol: t.label for t in tickers}, sess.session)
    for q in quotes.values():
        enrich_stock_info(q)
    indices = fetch_quotes(mcfg.get("indicators", {}), sess.session)
    futures = fetch_quotes(mcfg.get("futures", {}), sess.session) if mcfg.get("futures") else {}
    views = {t.symbol: fetch_analyst_view(t.symbol, sess.session, cfg) for t in tickers}
    return dict(session=sess, tickers=tickers, quotes=quotes, indices=indices, futures=futures, views=views)


def cmd_collect(cfg, args):
    data = collect_market(cfg)
    path = save_market(day_dir(args.day) / "market.json", **data)
    bad = [s for s, q in data["quotes"].items() if q.error or q.close is None]
    log.info("✅ %s 저장 (시세 실패: %s)", path.relative_to(ROOT), bad or "없음")


# ── 렌더링 / 전송 ─────────────────────────────────────────
def _git_pull():
    try:
        subprocess.run(["git", "pull", "--ff-only", "-q"], cwd=ROOT, timeout=60, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _send_time(cfg, tz) -> datetime:
    hh, mm = map(int, cfg.get("send_at", "08:50").split(":"))
    return datetime.now(tz).replace(hour=hh, minute=mm, second=0, microsecond=0)


def render_day(cfg, day: str, now: datetime) -> tuple[dict, list[Path], Path, Path | None]:
    d = day_dir(day)
    m = load_market(d / "market.json")
    a = load_analysis(d / "analysis.json") or {}
    ai_tickers = a.get("tickers", {})
    news = a.get("news") or {}
    if not a:
        m["session"].note = (m["session"].note + " · " if m["session"].note else "") + \
            "AI 분석이 준비되지 않아 시세·목표가만 전송"
    ctx = build_context(session_info=m["session"], report_dt=now, tickers=m["tickers"], quotes=m["quotes"],
                        indices=m["indices"], futures=m["futures"], views=m["views"],
                        ai_tickers=ai_tickers, news=news)
    ocfg = cfg.get("output", {})
    out = ROOT / ocfg.get("dir", "output") / day
    html_path = save_html(render_html(ctx, mode="page"), out, f"briefing_{day}.html")
    cards_src = save_html(render_html(ctx, mode="cards"), out, "_cards.html")
    from briefing.render import render_cards
    cards = render_cards(cards_src, out / "cards", int(ocfg.get("card_width", 1080)))
    pptx = None
    if ocfg.get("pptx"):
        from briefing.pptx_export import build_pptx
        pptx = build_pptx(cards, out / f"briefing_{day}.pptx")
    log.info("📁 카드 %d장 → %s", len(cards), out)
    return ctx, cards, html_path, pptx


def deliver(cfg, ctx, cards, html_path, pptx_path):
    dcfg, ocfg = cfg.get("delivery", {}), cfg.get("output", {})
    idx = " · ".join(f"{q.name} {q.change_pct:+.2f}%" for q in ctx["indices"][:2] if q.change_pct is not None)
    movers = sorted(ctx["stocks"], key=lambda s: abs(s["q"].change_pct or 0), reverse=True)[:3]
    mv = " / ".join(f"{s['t'].symbol} {s['q'].change_pct:+.1f}%" for s in movers if s["q"].change_pct is not None)
    caption = (f"<b>🇺🇸 미국증시 모닝 브리핑 {ctx['report_date']}</b>\n{ctx['session_label']}\n{idx}\n"
               f"관심종목 큰 변동: {mv}")
    if ctx.get("session_note"):
        caption += f"\n※ {ctx['session_note']}"
    attachments = [p for p in ((html_path if ocfg.get("html", True) else None), pptx_path) if p]
    if dcfg.get("telegram"):
        from briefing.delivery.telegram import Telegram
        tg = Telegram()
        tg.send_album(cards, caption=caption)
        for a in attachments:
            tg.send_document(a, caption="🔗 출처 링크 포함 전체 리포트" if a.suffix == ".html" else "📎 PPT 버전")
        log.info("✅ 텔레그램 전송 완료")
    if dcfg.get("email"):
        from briefing.delivery.email import send_email
        send_email(f"[미국증시 브리핑] {ctx['report_date']}", cards, attachments)
        log.info("✅ 이메일 전송 완료")


def cmd_deliver(cfg, args):
    tz = ZoneInfo(cfg.get("timezone", "Asia/Seoul"))
    day = args.day or today_kst()
    d = day_dir(day)
    if (d / "sent.txt").exists() and not args.force:
        log.info("이미 전송됨 (%s) — 건너뜀", d / "sent.txt")
        return
    send_at = _send_time(cfg, tz)
    deadline = send_at - timedelta(minutes=2)
    if not args.no_wait:  # Claude 분석 결과 기다리기
        while not (d / "analysis.json").exists() and datetime.now(tz) < deadline:
            log.info("⏳ analysis.json 대기 중… (마감 %s)", deadline.strftime("%H:%M"))
            time.sleep(60)
            _git_pull()
    if not (d / "market.json").exists():  # 수집 단계가 실패했으면 여기서 직접 수집
        log.warning("market.json 없음 → 직접 수집")
        save_market(d / "market.json", **collect_market(cfg))
    ctx, cards, html_path, pptx = render_day(cfg, day, datetime.now(tz))
    if args.dry_run:
        log.info("dry-run: 전송 생략")
        return
    if not args.no_wait:
        secs = (send_at - datetime.now(tz)).total_seconds()
        if 0 < secs < 3 * 3600:
            log.info("⏳ %s 까지 %.0f분 대기", send_at.strftime("%H:%M"), secs / 60)
            time.sleep(secs)
    deliver(cfg, ctx, cards, html_path, pptx)
    (d / "sent.txt").write_text(datetime.now(tz).isoformat(timespec="seconds"), encoding="utf-8")


def cmd_render(cfg, args):
    tz = ZoneInfo(cfg.get("timezone", "Asia/Seoul"))
    render_day(cfg, args.day or today_kst(), datetime.now(tz))


def cmd_build_web_market(cfg, args):
    from briefing.web_market import build_from_web
    d = day_dir(args.day)
    p = build_from_web(d / "market_web.json", d / "market.json")
    log.info("✅ %s 생성 (웹 시세)", p.relative_to(ROOT))


def cmd_mock(cfg, args):
    from briefing import mock
    from briefing.store import save_market as _save

    tz = ZoneInfo(cfg.get("timezone", "Asia/Seoul"))
    day = "mock"
    tickers = load_tickers(cfg)
    sess = last_completed_session()
    mcfg = cfg.get("market", {})
    quotes = mock.mock_quotes(tickers, sess.session)
    _save(day_dir(day) / "market.json", session=sess, tickers=tickers, quotes=quotes,
          indices=mock.mock_indices(mcfg.get("indicators", {})), futures=mock.mock_indices(mcfg.get("futures", {})),
          views=mock.mock_views(tickers, quotes))
    import json
    (day_dir(day) / "analysis.json").write_text(json.dumps(
        {"tickers": mock.mock_ai_tickers(tickers, quotes), "news": mock.mock_news()}, ensure_ascii=False), "utf-8")
    ctx, cards, html_path, pptx = render_day(cfg, day, datetime.now(tz))
    if args.send:
        deliver(cfg, ctx, cards, html_path, pptx)


def cmd_api(cfg, args):
    """Claude API 크레딧으로 수집·분석·전송을 한 번에 (선택 모드)."""
    from briefing.ai_analyst import ClaudeAnalyst

    day = args.day or today_kst()
    data = collect_market(cfg)
    save_market(day_dir(day) / "market.json", **data)
    ai = ClaudeAnalyst(cfg)
    ai_t = ai.analyze_tickers([(t, data["quotes"][t.symbol], data["views"][t.symbol]) for t in data["tickers"]],
                              data["session"].session)
    news = ai.top_news(data["session"].session, data["indices"])
    import json
    (day_dir(day) / "analysis.json").write_text(json.dumps({"tickers": ai_t, "news": news}, ensure_ascii=False), "utf-8")
    log.info("API 사용량 %s ≈ $%.3f", ai.usage, ai.estimated_cost_usd())
    args.no_wait = True
    cmd_deliver(cfg, args)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="미국주식 데일리 브리핑")
    ap.add_argument("command", choices=["collect", "deliver", "render", "build-web-market", "mock", "api"])
    ap.add_argument("--day", help="data 폴더 날짜 (기본: 오늘 KST)")
    ap.add_argument("--no-wait", action="store_true", help="대기 없이 즉시 진행")
    ap.add_argument("--dry-run", action="store_true", help="전송하지 않음")
    ap.add_argument("--force", action="store_true", help="이미 전송했어도 다시 전송")
    ap.add_argument("--send", action="store_true", help="mock 결과도 전송")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    load_dotenv(ROOT / ".env")
    cfg = load_config()
    {
        "collect": cmd_collect, "deliver": cmd_deliver, "render": cmd_render,
        "build-web-market": cmd_build_web_market, "mock": cmd_mock, "api": cmd_api,
    }[args.command](cfg, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
