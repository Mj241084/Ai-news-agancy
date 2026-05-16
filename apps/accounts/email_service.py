from __future__ import annotations
from django.conf import settings
from django.core.mail import EmailMultiAlternatives


def build_verification_code_email(code: str) -> tuple[str, str, str]:
    subject = f"کد تایید ورود به {settings.SITE_NAME}"
    text_body = (
        f"کد تایید شما: {code}\n"
        f"این کد تا 5 دقیقه معتبر است.\n"
        f"اگر شما درخواست نداده‌اید این پیام را نادیده بگیرید."
    )

    html_body = f"""
    <html>
      <body style=\"font-family:Tahoma,Arial,sans-serif;direction:rtl;text-align:right;\">
        <h2 style=\"margin:0 0 12px;\">{settings.SITE_NAME}</h2>
        <p style=\"margin:0 0 10px;\">کد تایید شما:</p>
        <p style=\"font-size:28px;font-weight:bold;letter-spacing:3px;margin:0 0 10px;\">{code}</p>
        <p style=\"color:#444;margin:0 0 8px;\">این کد فقط تا 5 دقیقه معتبر است.</p>
        <p style=\"color:#666;margin:0;\">اگر شما این درخواست را ارسال نکرده‌اید، این ایمیل را نادیده بگیرید.</p>
      </body>
    </html>
    """.strip()

    return subject, html_body, text_body


def send_email(to: str, subject: str, html_body: str, text_body: str | None = None) -> int:
    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body or "",
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to],
    )
    message.attach_alternative(html_body, "text/html")
    return message.send(fail_silently=False)
