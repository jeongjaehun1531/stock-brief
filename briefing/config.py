"""설정(config.yaml)과 관심종목(tickers.md) 로딩."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

# Yahoo 티커: 대문자/숫자/점/하이픈/캐럿/등호 (예: BRK-B, ^GSPC, KRW=X)
_TICKER_RE = re.compile(r"^[A-Z0-9^][A-Z0-9.\-=^]{0,14}$")


@dataclass
class Ticker:
    symbol: str
    name: str = ""
    memo: str = ""

    @property
    def label(self) -> str:
        return self.name or self.symbol


def load_config(path: str | Path | None = None) -> dict:
    path = Path(path) if path else ROOT / "config.yaml"
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    # 환경변수로 일부 덮어쓰기 (GitHub Actions 등에서 편의용)
    if os.getenv("BRIEFING_MODEL"):
        cfg.setdefault("claude", {})["model"] = os.environ["BRIEFING_MODEL"]
    if os.getenv("BRIEFING_SEND_AT"):
        cfg["send_at"] = os.environ["BRIEFING_SEND_AT"]
    return cfg


def parse_tickers(text: str) -> list[Ticker]:
    """tickers.md 파싱.

    인식 규칙
      - `-` 또는 `*` 로 시작하는 목록 줄만 인식
      - `- NVDA | 엔비디아 | 메모` 형식 (이름·메모 생략 가능)
      - `#` 으로 시작하는 줄, `~~취소선~~` 줄, 코드블록 내부는 무시
      - 중복 티커는 첫 번째만 사용
    """
    tickers: list[Ticker] = []
    seen: set[str] = set()
    in_code = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not line or line.startswith("#") or line.startswith(">"):
            continue
        if not (line.startswith("- ") or line.startswith("* ")):
            continue
        body = line[2:].strip()
        if body.startswith("~~"):
            continue
        # 줄 끝 주석 제거 ("  # ..." 또는 "← ...")
        body = re.split(r"\s+#\s|←", body, maxsplit=1)[0].strip()
        parts = [p.strip() for p in body.split("|")]
        symbol = parts[0].upper().replace(" ", "")
        if not _TICKER_RE.match(symbol) or symbol in seen:
            continue
        seen.add(symbol)
        tickers.append(
            Ticker(
                symbol=symbol,
                name=parts[1] if len(parts) > 1 else "",
                memo=parts[2] if len(parts) > 2 else "",
            )
        )
    return tickers


def load_tickers(cfg: dict) -> list[Ticker]:
    path = ROOT / cfg.get("tickers_file", "tickers.md")
    if not path.exists():
        raise FileNotFoundError(f"관심종목 파일이 없습니다: {path}")
    tickers = parse_tickers(path.read_text(encoding="utf-8"))
    if not tickers:
        raise ValueError(f"{path.name} 에서 인식된 티커가 없습니다. '- NVDA' 형식인지 확인하세요.")
    return tickers
