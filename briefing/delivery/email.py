"""이메일 전송(선택): 카드 이미지를 본문에 세로로 인라인 + HTML/PPTX 첨부."""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path


def send_email(subject: str, cards: list[Path], attachments: list[Path]) -> None:
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user, pw = os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"]
    to = os.environ.get("MAIL_TO", user)

    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.set_content("HTML 메일을 지원하는 앱에서 확인하세요.")
    cids = [make_msgid() for _ in cards]
    imgs = "".join(
        f'<img src="cid:{c[1:-1]}" style="width:100%;max-width:540px;display:block;margin:0 auto 8px">'
        for c in cids
    )
    msg.add_alternative(f'<div style="background:#0A0D14;padding:8px 0">{imgs}</div>', subtype="html")
    html_part = msg.get_payload()[1]
    for cid, p in zip(cids, cards):
        html_part.add_related(p.read_bytes(), "image", "png", cid=cid)
    for a in attachments:
        sub = "html" if a.suffix == ".html" else "vnd.openxmlformats-officedocument.presentationml.presentation"
        maintype = "text" if a.suffix == ".html" else "application"
        msg.add_attachment(a.read_bytes(), maintype=maintype, subtype=sub, filename=a.name)

    with smtplib.SMTP(host, port, timeout=60) as s:
        s.starttls()
        s.login(user, pw)
        s.send_message(msg)
