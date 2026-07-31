from __future__ import annotations

import smtplib
from email.message import EmailMessage

from repo_courier.config import PushConfig
from repo_courier.pushers import configured_pushers
from repo_courier.pushers.email import EmailPusher


class FakeSMTP:
    def __init__(self, fail_login: bool = False) -> None:
        self.fail_login = fail_login
        self.login_args: tuple[str, str] = ()
        self.sent: list[tuple[EmailMessage, str, list[str]]] = []
        self.quit_called = False

    def login(self, username: str, auth_code: str) -> None:
        self.login_args = (username, auth_code)
        if self.fail_login:
            raise smtplib.SMTPAuthenticationError(535, b"authentication failed")

    def send_message(
        self, message: EmailMessage, from_addr: str | None = None, to_addrs: list[str] | None = None
    ) -> None:
        self.sent.append((message, from_addr or "", to_addrs or []))

    def quit(self) -> None:
        self.quit_called = True


def test_email_pusher_sends_digest_with_login_credentials() -> None:
    smtp = FakeSMTP()
    pusher = EmailPusher(
        "smtp.example.com",
        465,
        "sender@example.com",
        "auth-code",
        "a@example.com, b@example.com",
        smtp=smtp,
    )

    result = pusher.send("RepoCourier 日报", "今日精选内容")

    assert result.channel == "email"
    assert result.success is True
    assert result.detail == "ok"
    assert smtp.login_args == ("sender@example.com", "auth-code")
    message, from_addr, to_addrs = smtp.sent[0]
    assert from_addr == "sender@example.com"
    assert to_addrs == ["a@example.com", "b@example.com"]
    assert message["Subject"] == "RepoCourier 日报"
    assert message["To"] == "a@example.com, b@example.com"
    assert message.is_multipart()
    plain = message.get_body(preferencelist=("plain",))
    assert plain.get_content().strip() == "今日精选内容"
    assert message.get_body(preferencelist=("html",)) is not None


def test_email_pusher_sends_html_alternative_with_converted_links() -> None:
    smtp = FakeSMTP()
    pusher = EmailPusher(
        "smtp.example.com", 465, "sender@example.com", "auth-code", "a@example.com", smtp=smtp
    )

    pusher.send(
        "标题",
        "1. [acme/agent](https://github.com/acme/agent)\n"
        "为什么：关注 <AI> 模型 & MCP\n"
        "https://example.com/plain",
    )

    message = smtp.sent[0][0]
    plain = message.get_body(preferencelist=("plain",))
    assert plain.get_content().strip() == (
        "1. [acme/agent](https://github.com/acme/agent)\n"
        "为什么：关注 <AI> 模型 & MCP\n"
        "https://example.com/plain"
    )
    html_content = message.get_body(preferencelist=("html",)).get_content()
    assert '<a href="https://github.com/acme/agent">acme/agent</a>' in html_content
    assert '<a href="https://example.com/plain">https://example.com/plain</a>' in html_content
    assert "关注 &lt;AI&gt; 模型 &amp; MCP" in html_content


def test_email_pusher_does_not_quit_injected_smtp() -> None:
    smtp = FakeSMTP()
    pusher = EmailPusher(
        "smtp.example.com", 465, "sender@example.com", "auth-code", "a@example.com", smtp=smtp
    )

    pusher.send("标题", "正文")

    assert smtp.quit_called is False


def test_email_pusher_auth_failure_returns_result_without_leaking_auth_code() -> None:
    smtp = FakeSMTP(fail_login=True)
    pusher = EmailPusher(
        "smtp.example.com", 465, "sender@example.com", "super-secret", "a@example.com", smtp=smtp
    )

    result = pusher.send("标题", "正文")

    assert result.success is False
    assert "super-secret" not in result.detail
    assert result.detail


def test_email_pusher_uses_smtp_ssl_by_default(monkeypatch) -> None:
    created: dict[str, object] = {}

    class FakeSMTPSSL:
        def __init__(self, host: str, port: int, timeout: float) -> None:
            created["host"] = host
            created["port"] = port
            created["ssl"] = True

        def login(self, username: str, auth_code: str) -> None:
            pass

        def send_message(
            self,
            message: EmailMessage,
            from_addr: str | None = None,
            to_addrs: list[str] | None = None,
        ) -> None:
            pass

        def quit(self) -> None:
            created["quit"] = True

    monkeypatch.setattr("repo_courier.pushers.email.smtplib.SMTP_SSL", FakeSMTPSSL)
    pusher = EmailPusher(
        "smtp.example.com", 465, "sender@example.com", "auth-code", "a@example.com"
    )

    result = pusher.send("标题", "正文")

    assert result.success is True
    assert created["ssl"] is True
    assert created["host"] == "smtp.example.com"
    assert created["port"] == 465
    assert created["quit"] is True


def test_email_pusher_uses_starttls_when_ssl_disabled(monkeypatch) -> None:
    created: dict[str, object] = {}

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: float) -> None:
            created["ssl"] = False
            created["host"] = host
            created["port"] = port

        def starttls(self) -> None:
            created["starttls"] = True

        def login(self, username: str, auth_code: str) -> None:
            pass

        def send_message(
            self,
            message: EmailMessage,
            from_addr: str | None = None,
            to_addrs: list[str] | None = None,
        ) -> None:
            pass

        def quit(self) -> None:
            created["quit"] = True

    monkeypatch.setattr("repo_courier.pushers.email.smtplib.SMTP", FakeSMTP)
    pusher = EmailPusher(
        "smtp.example.com", 587, "sender@example.com", "auth-code", "a@example.com", use_ssl=False
    )

    result = pusher.send("标题", "正文")

    assert result.success is True
    assert created["ssl"] is False
    assert created["starttls"] is True
    assert created["port"] == 587
    assert created["quit"] is True


def test_configured_pushers_includes_email_when_fully_configured() -> None:
    config = PushConfig(
        email_smtp_host="smtp.example.com",
        email_username="sender@example.com",
        email_auth_code="auth-code",
        email_to="a@example.com",
    )

    pushers = configured_pushers(config)

    assert any(isinstance(pusher, EmailPusher) for pusher in pushers)


def test_configured_pushers_skips_email_when_partially_configured() -> None:
    assert configured_pushers(PushConfig(email_smtp_host="smtp.example.com")) == []
    assert configured_pushers(PushConfig(email_username="sender@example.com")) == []
    assert configured_pushers(PushConfig(email_auth_code="auth-code")) == []
    assert configured_pushers(PushConfig(email_to="a@example.com")) == []
