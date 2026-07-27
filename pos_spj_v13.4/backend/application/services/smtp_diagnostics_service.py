"""SMTP application service — keeps smtplib out of PyQt widgets (FASE 8)."""

from __future__ import annotations

from backend.application.dto.diagnostics import DiagnosticResult


class SMTPSettingsApplicationService:
    """Sends a test email so the UI only issues a command and renders the result."""

    def send_test_email(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        use_tls: bool,
        recipient: str,
    ) -> DiagnosticResult:
        host = (host or "").strip()
        username = (username or "").strip()
        recipient = (recipient or "").strip() or username
        if not host or not username:
            return DiagnosticResult.failure("Completa host y usuario primero.")
        try:
            import smtplib
            import ssl
            from email.mime.text import MIMEText

            msg = MIMEText("Correo de prueba desde SPJ POS v13. Todo funciona correctamente.")
            msg["Subject"] = "SPJ POS — Prueba de correo"
            msg["From"] = username
            msg["To"] = recipient
            ctx = ssl.create_default_context()
            with smtplib.SMTP(host, int(port), timeout=10) as server:
                server.ehlo()
                if use_tls:
                    server.starttls(context=ctx)
                server.login(username, password)
                server.sendmail(username, [recipient], msg.as_string())
            return DiagnosticResult.success(f"Correo de prueba enviado a {recipient}.")
        except Exception as exc:  # explicit, traceable failure
            return DiagnosticResult.failure(f"Error SMTP: {exc}")
