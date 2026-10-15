"""텔레그램 전송: 요약 메시지 + 카드 앨범(최대 10장씩) + 문서 첨부."""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)
API = "https://api.telegram.org/bot{token}/{method}"


class Telegram:
    def __init__(self, token: str | None = None, chat_id: str | None = None):
        tok = (token or os.environ.get("TELEGRAM_BOT_TOKEN", "")).strip().strip('"\'')
        if tok.lower().startswith("bot"):        # 'bot123:AA…' 처럼 접두어까지 복사한 경우
            tok = tok[3:]
        self.token = tok
        self.chat_id = (chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")).strip().strip('"\'')
        missing = [n for n, v in (("TELEGRAM_BOT_TOKEN", self.token), ("TELEGRAM_CHAT_ID", self.chat_id)) if not v]
        if missing:
            raise RuntimeError(f"{', '.join(missing)} 값이 비어 있음 → Settings > Secrets and variables > Actions > "
                               "Secrets 탭의 'Repository secrets' 에 정확한 이름으로 등록됐는지 확인")
        self._preflight()

    def _preflight(self):
        """토큰 형식·유효성 사전 점검 → 원인을 알 수 있는 오류 메시지."""
        if ":" not in self.token:
            raise RuntimeError(f"봇 토큰 형식 오류: '숫자:영문' 형태여야 함 (현재 길이 {len(self.token)}자, ':' 없음)")
        r = requests.get(API.format(token=self.token, method="getMe"), timeout=30)
        if r.status_code in (401, 404):
            raise RuntimeError(f"봇 토큰이 유효하지 않음 (HTTP {r.status_code}). BotFather 토큰을 다시 복사해 등록하세요. "
                               f"(길이 {len(self.token)}자, 앞부분 {self.token.split(':')[0][:4]}…)")
        log.info("텔레그램 봇 확인: @%s", r.json().get("result", {}).get("username"))

    def _call(self, method: str, data=None, files=None, retries=3):
        url = API.format(token=self.token, method=method)
        for i in range(retries):
            r = requests.post(url, data=data, files=files, timeout=60)
            if r.ok:
                return r.json()
            if r.status_code == 429:  # flood control
                wait = r.json().get("parameters", {}).get("retry_after", 5)
                time.sleep(wait + 1)
                continue
            log.warning("Telegram %s 실패 %s: %s", method, r.status_code, r.text[:200])
            if r.status_code == 400 and "chat not found" in r.text:
                raise RuntimeError("TELEGRAM_CHAT_ID 가 올바르지 않음: 봇에게 먼저 메시지를 보냈는지, getUpdates 의 chat.id 숫자인지 확인")
            time.sleep(2 * (i + 1))
        raise RuntimeError(f"Telegram {method} 전송 실패: HTTP {r.status_code} {r.text[:200]}")

    def send_text(self, text: str):
        return self._call("sendMessage", data={
            "chat_id": self.chat_id, "text": text, "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        })

    def send_album(self, images: list[Path], caption: str | None = None):
        """sendMediaGroup: 한 번에 2~10장. 스와이프로 넘겨보기 좋음."""
        for start in range(0, len(images), 10):
            chunk = images[start:start + 10]
            if len(chunk) == 1:
                with open(chunk[0], "rb") as f:
                    self._call("sendPhoto", data={"chat_id": self.chat_id}, files={"photo": f})
                continue
            media, files = [], {}
            for i, p in enumerate(chunk):
                key = f"f{i}"
                item = {"type": "photo", "media": f"attach://{key}"}
                if i == 0 and start == 0 and caption:
                    item |= {"caption": caption, "parse_mode": "HTML"}
                media.append(item)
                files[key] = open(p, "rb")
            try:
                self._call("sendMediaGroup", data={"chat_id": self.chat_id, "media": json.dumps(media)}, files=files)
            finally:
                for f in files.values():
                    f.close()

    def send_document(self, path: Path, caption: str = ""):
        with open(path, "rb") as f:
            return self._call("sendDocument", data={"chat_id": self.chat_id, "caption": caption},
                              files={"document": (path.name, f)})
