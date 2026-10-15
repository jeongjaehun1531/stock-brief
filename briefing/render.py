"""HTML → 카드별 PNG (Playwright/Chromium)."""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)


def render_cards(html_path: Path, out_dir: Path, width_px: int = 1080) -> list[Path]:
    """각 <section class="card"> 를 개별 PNG 로 캡처. CSS 폭 480px × 배율 → width_px."""
    from playwright.sync_api import sync_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    scale = width_px / 480
    paths: list[Path] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 480, "height": 900}, device_scale_factor=scale)
        page.goto(html_path.resolve().as_uri(), wait_until="networkidle", timeout=30000)
        page.evaluate("document.fonts.ready")
        for el in page.query_selector_all("section.card"):
            name = el.get_attribute("data-card") or f"card_{len(paths):02d}"
            path = out_dir / f"{name}.png"
            el.screenshot(path=str(path))
            paths.append(path)
        browser.close()
    log.info("카드 %d장 렌더링 완료", len(paths))
    return paths
