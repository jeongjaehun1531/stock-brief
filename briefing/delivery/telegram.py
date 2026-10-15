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
        self.token = token or os.environ["TELEGRAM_BOT_TOKEN"]
        self.chat_id = chat_id or os.environ["TELEGRAM_CHAT_ID"]

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
            time.sleep(2 * (i + 1))
        raise RuntimeError(f"Telegram {method} 전송 실패")

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
