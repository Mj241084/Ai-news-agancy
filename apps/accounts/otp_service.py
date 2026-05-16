from __future__ import annotations
import hashlib
import hmac
import random
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db.models import F
from django.utils import timezone

from apps.accounts.email_service import build_verification_code_email, send_email
from apps.accounts.models import EmailOTP


class OTPError(Exception):
    pass


class OTPRateLimited(OTPError):
    pass


class OTPInvalid(OTPError):
    pass


class OTPExpired(OTPError):
    pass


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _hash_code(email: str, code: str) -> str:
    payload = f"{email}:{code}".encode("utf-8")
    return hmac.new(settings.SECRET_KEY.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _otp_rate_limit_key(email: str) -> str:
    return f"otp:ratelimit:{email}"


def generate_otp_code() -> str:
    return f"{random.randint(0, 999999):06d}"


def create_otp(email: str, *, meta: dict | None = None, send: bool = True) -> EmailOTP:
    normalized_email = _normalize_email(email)
    rate_key = _otp_rate_limit_key(normalized_email)

    if cache.get(rate_key):
        raise OTPRateLimited("Please wait before requesting another code.")

    code = generate_otp_code()
    now = timezone.now()
    expires_at = now + timedelta(seconds=settings.OTP_EXPIRE_SECONDS)

    otp = EmailOTP.objects.create(
        email=normalized_email,
        code_hash=_hash_code(normalized_email, code),
        expires_at=expires_at,
        meta=meta or {},
    )

    cache.set(rate_key, 1, timeout=settings.OTP_RATE_LIMIT_SECONDS)

    if send:
        subject, html_body, text_body = build_verification_code_email(code)
        try:
            send_email(normalized_email, subject, html_body, text_body)
        except Exception:
            otp.delete()
            cache.delete(rate_key)
            raise

    return otp


def verify_otp(email: str, code: str) -> EmailOTP:
    normalized_email = _normalize_email(email)
    now = timezone.now()

    otp = (
        EmailOTP.objects.filter(email=normalized_email, used_at__isnull=True)
        .order_by("-created_at")
        .first()
    )

    if otp is None:
        raise OTPInvalid("No active verification code found.")

    if otp.attempt_count >= settings.OTP_MAX_ATTEMPTS:
        raise OTPInvalid("Maximum verification attempts exceeded.")

    if now >= otp.expires_at:
        raise OTPExpired("Verification code has expired.")

    expected_hash = _hash_code(normalized_email, (code or "").strip())
    if not hmac.compare_digest(otp.code_hash, expected_hash):
        EmailOTP.objects.filter(pk=otp.pk).update(attempt_count=F("attempt_count") + 1)
        otp.refresh_from_db(fields=["attempt_count"])
        raise OTPInvalid("Verification code is invalid.")

    EmailOTP.objects.filter(pk=otp.pk, used_at__isnull=True).update(used_at=now)
    otp.used_at = now
    return otp
