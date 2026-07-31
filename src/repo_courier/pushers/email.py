from __future__ import annotations

import html
import re
import smtplib
from email.message import EmailMessage

from .base import PushResult

_MARKDOWN_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")
_BARE_URL = re.compile(r'(?<![\w"])(https?://[^\s<>()，。！？；]+)(?=[\s<>()，。！？；]|$)')

_BODY_STYLE = (
    "font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, "
    "'PingFang SC', 'Microsoft YaHei', sans-serif; line-height: 1.6;"
)
_PRE_STYLE = "white-space: pre-wrap; word-break: break-word; font-family: inherit;"


class EmailPusher:
    channel = "email"

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        username: str,
        auth_code: str,
        to_addr: str,
        use_ssl: bool = True,
        smtp: smtplib.SMTP | None = None,
    ) -> None:
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.auth_code = auth_code
        self.to_addr = to_addr
        self.use_ssl = use_ssl
        self._smtp = smtp

    def send(self, title: str, content: str) -> PushResult:
        try:
            smtp = self._connect()
            try:
                smtp.login(self.username, self.auth_code)
                smtp.send_message(
                    self._build_message(title, content),
                    from_addr=self.username,
                    to_addrs=self._recipients(),
                )
            finally:
                if self._smtp is None:
                    smtp.quit()
            return PushResult(self.channel, True, "ok")
        except (smtplib.SMTPException, OSError, ValueError) as exc:
            return PushResult(self.channel, False, str(exc))

    def _connect(self) -> smtplib.SMTP:
        if self._smtp is not None:
            return self._smtp
        if self.use_ssl:
            return smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=20)
        smtp = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=20)
        smtp.starttls()
        return smtp

    def _build_message(self, title: str, content: str) -> EmailMessage:
        message = EmailMessage()
        message["Subject"] = title
        message["From"] = self.username
        message["To"] = ", ".join(self._recipients())
        message.set_content(content)
        message.add_alternative(self._to_html(content), subtype="html")
        return message

    def _to_html(self, content: str) -> str:
        escaped = html.escape(content)
        escaped = _MARKDOWN_LINK.sub(r'<a href="\2">\1</a>', escaped)
        escaped = _BARE_URL.sub(r'<a href="\1">\1</a>', escaped)
        return (
            f'<html><body style="{_BODY_STYLE}">'
            f'<pre style="{_PRE_STYLE}">{escaped}</pre>'
            "</body></html>"
        )

    def _recipients(self) -> list[str]:
        return [addr.strip() for addr in self.to_addr.split(",") if addr.strip()]
