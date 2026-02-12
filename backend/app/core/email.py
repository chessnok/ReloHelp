import smtplib
from abc import ABC, abstractmethod
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import httpx
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import settings
from app.core.logger import logger


class EmailProvider(ABC):
    @abstractmethod
    async def send_email(
        self, to_email: str, subject: str, html_content: str, text_content: str = None
    ) -> None:
        pass


class SMTPEmailProvider(EmailProvider):
    async def send_email(
        self, to_email: str, subject: str, html_content: str, text_content: str = None
    ) -> None:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM_EMAIL}>"
        msg["To"] = to_email
        msg["Subject"] = subject

        if text_content:
            msg.attach(MIMEText(text_content, "plain"))

        msg.attach(MIMEText(html_content, "html"))

        try:
            # Note: smtplib is blocking. In a high-load async app, run this in a threadpool.
            # For simplicity here, we'll keep it direct, but be aware it blocks the event loop.
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
            if settings.SMTP_TLS:
                server.starttls()

            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)

            server.send_message(msg)
            server.quit()
            logger.info(f"Email sent via SMTP to {to_email}")
        except Exception as e:
            logger.error(f"Failed to send email via SMTP: {e}")
            raise


class ResendEmailProvider(EmailProvider):
    async def send_email(
        self, to_email: str, subject: str, html_content: str, text_content: str = None
    ) -> None:
        if not settings.RESEND_API_KEY:
            logger.error("Resend API key is missing")
            raise ValueError("Resend API key is missing")

        headers = {
            "Authorization": f"Bearer {settings.RESEND_API_KEY}",
            "Content-Type": "application/json",
        }

        payload = {
            "from": f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM_EMAIL}>",
            "to": [to_email],
            "subject": subject,
            "html": html_content,
        }

        if text_content:
            payload["text"] = text_content

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    "https://api.resend.com/emails", json=payload, headers=headers
                )
                response.raise_for_status()
                logger.info(f"Email sent via Resend to {to_email}")
            except httpx.HTTPStatusError as e:
                logger.error(f"Resend API error: {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"Failed to send email via Resend: {e}")
                raise


class EmailService:
    def __init__(self):
        self.provider: EmailProvider
        if settings.EMAIL_PROVIDER == "resend":
            self.provider = ResendEmailProvider()
        else:
            self.provider = SMTPEmailProvider()

        self.template_env = Environment(
            loader=FileSystemLoader(Path(__file__).parent.parent / "templates"),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def render_template(self, template_name: str, context: dict[str, Any]) -> str:
        template = self.template_env.get_template(template_name)
        return template.render(context)

    async def send_password_reset_email(self, to_email: str, token: str) -> None:
        subject = "Password Reset Request"
        reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"

        context = {"token": token, "link": reset_link, "subject": subject}

        html_content = self.render_template("email/password_reset.html", context)
        text_content = self.render_template("email/password_reset.txt", context)

        await self.provider.send_email(to_email, subject, html_content, text_content)

    async def send_verification_email(self, to_email: str, token: str) -> None:
        subject = "Verify Your Email"
        verify_link = f"{settings.FRONTEND_URL}/verify-email?token={token}"

        context = {"token": token, "link": verify_link, "subject": subject}

        html_content = self.render_template("email/verification.html", context)
        text_content = self.render_template("email/verification.txt", context)

        await self.provider.send_email(to_email, subject, html_content, text_content)


email_service = EmailService()
