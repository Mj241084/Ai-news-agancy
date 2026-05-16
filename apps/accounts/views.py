from __future__ import annotations

import json
from datetime import timedelta

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.accounts.models import UserProfile
from apps.accounts.otp_service import OTPExpired, OTPInvalid, OTPRateLimited, create_otp, verify_otp
from apps.seo.context import build_seo_context

SIGNUP_PENDING_SESSION_KEY = "signup_pending"
SIGNUP_PENDING_MAX_AGE_SECONDS = 15 * 60


def _parse_payload(request) -> dict:
    if request.content_type and "application/json" in request.content_type:
        try:
            body = request.body.decode("utf-8")
            return json.loads(body) if body else {}
        except json.JSONDecodeError:
            return {}
    return request.POST.dict()


def _validate_email_field(email: str) -> str | None:
    email = (email or "").strip().lower()
    if not email:
        return None
    try:
        validate_email(email)
        return email
    except Exception:
        return None


def _wants_json(request) -> bool:
    accept = request.headers.get("Accept", "")
    return (
        "application/json" in accept
        or request.content_type == "application/json"
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
    )


def _json_response(payload: dict, *, status: int = 200):
    response = JsonResponse(payload, status=status)
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


def _safe_next_url(request, raw_next: str | None = None) -> str:
    candidate = (raw_next or request.GET.get("next") or request.POST.get("next") or "").strip()
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return reverse("core:home")


def _otp_meta_from_request(request) -> dict:
    return {
        "ip": request.META.get("REMOTE_ADDR"),
        "user_agent": request.META.get("HTTP_USER_AGENT", ""),
    }


def _send_code(email: str, request) -> tuple[bool, str | None, int]:
    try:
        create_otp(email=email, meta=_otp_meta_from_request(request), send=True)
        return True, None, 200
    except OTPRateLimited as exc:
        return False, str(exc), 429
    except Exception as exc:
        return False, f"Unable to send verification code: {exc}", 500


def _verify_code(email: str, code: str) -> tuple[bool, str | None, int]:
    try:
        verify_otp(email=email, code=code)
        return True, None, 200
    except OTPExpired as exc:
        return False, str(exc), 410
    except OTPInvalid as exc:
        return False, str(exc), 400


def _build_unique_username(email: str) -> str:
    user_model = get_user_model()
    username = email
    if not user_model.objects.filter(username=username).exists():
        return username

    local, _, domain = email.partition("@")
    base = local or "user"
    counter = 2
    while True:
        candidate = f"{base}-{counter}@{domain}" if domain else f"{base}-{counter}"
        if not user_model.objects.filter(username=candidate).exists():
            return candidate
        counter += 1


def _set_signup_pending(request, *, email: str) -> None:
    request.session[SIGNUP_PENDING_SESSION_KEY] = {
        "email": email,
        "verified_at": timezone.now().isoformat(),
    }
    request.session.modified = True


def _clear_signup_pending(request) -> None:
    request.session.pop(SIGNUP_PENDING_SESSION_KEY, None)
    request.session.modified = True


def _get_signup_pending_email(request) -> str | None:
    payload = request.session.get(SIGNUP_PENDING_SESSION_KEY) or {}
    email = (payload.get("email") or "").strip().lower()
    verified_at_raw = payload.get("verified_at")

    if not email or not verified_at_raw:
        return None

    try:
        verified_at = timezone.datetime.fromisoformat(verified_at_raw)
        if timezone.is_naive(verified_at):
            verified_at = timezone.make_aware(verified_at, timezone.get_current_timezone())
    except Exception:
        return None

    if timezone.now() - verified_at > timedelta(seconds=SIGNUP_PENDING_MAX_AGE_SECONDS):
        _clear_signup_pending(request)
        return None

    return email


def _build_auth_context(
    request,
    *,
    auth_tab: str,
    signup_stage: str,
    signup_email: str = "",
    login_email: str = "",
    auth_error: str | None = None,
    auth_success: str | None = None,
):
    pending_email = _get_signup_pending_email(request)
    if pending_email and signup_stage == "request":
        signup_stage = "complete"
        signup_email = pending_email

    context = {
        "auth_tab": auth_tab,
        "signup_stage": signup_stage,
        "signup_email": signup_email,
        "login_email": login_email,
        "auth_error": auth_error,
        "auth_success": auth_success,
        "next_url": _safe_next_url(request),
        "active_nav": "auth",
        "seo": build_seo_context(request, page_type="auth"),
    }
    return context


def _render_auth(
    request,
    *,
    auth_tab: str,
    signup_stage: str,
    signup_email: str = "",
    login_email: str = "",
    auth_error: str | None = None,
    auth_success: str | None = None,
    status: int = 200,
):
    context = _build_auth_context(
        request,
        auth_tab=auth_tab,
        signup_stage=signup_stage,
        signup_email=signup_email,
        login_email=login_email,
        auth_error=auth_error,
        auth_success=auth_success,
    )
    return render(request, "pages/auth.html", context, status=status)


@require_GET
def login_view(request):
    return _render_auth(request, auth_tab="login", signup_stage="request")


@require_GET
def register_view(request):
    stage = (request.GET.get("stage") or "request").strip().lower()
    if stage not in {"request", "verify", "complete"}:
        stage = "request"

    email = (request.GET.get("email") or "").strip().lower()
    if stage == "complete":
        pending_email = _get_signup_pending_email(request)
        if not pending_email:
            stage = "request"
            email = ""
        else:
            email = pending_email

    return _render_auth(
        request,
        auth_tab="signup",
        signup_stage=stage,
        signup_email=email,
    )


@require_http_methods(["GET", "POST"])
def verify_email_view(request):
    if request.method == "POST":
        return verify_code_view(request)

    email = (request.GET.get("email") or "").strip().lower()
    return _render_auth(
        request,
        auth_tab="signup",
        signup_stage="verify",
        signup_email=email,
    )


@require_POST
def request_code_view(request):
    payload = _parse_payload(request)
    email = _validate_email_field(payload.get("email", ""))
    if not email:
        if _wants_json(request):
            return _json_response({"ok": False, "error": "A valid email is required."}, status=400)
        return _render_auth(
            request,
            auth_tab="signup",
            signup_stage="request",
            signup_email="",
            auth_error="ایمیل معتبر وارد کنید.",
            status=400,
        )

    ok, error, status_code = _send_code(email, request)
    if not ok:
        if _wants_json(request):
            return _json_response({"ok": False, "error": error}, status=status_code)
        return _render_auth(
            request,
            auth_tab="signup",
            signup_stage="request",
            signup_email=email,
            auth_error=error,
            status=status_code,
        )

    if _wants_json(request):
        return _json_response({"ok": True, "message": "Verification code sent.", "email": email})

    next_url = _safe_next_url(request)
    verify_url = f"{reverse('accounts:register')}?stage=verify&email={email}&next={next_url}"
    return redirect(verify_url)


@require_POST
def verify_code_view(request):
    payload = _parse_payload(request)
    email = _validate_email_field(payload.get("email", ""))
    code = (payload.get("code") or "").strip()

    if not email or not code:
        if _wants_json(request):
            return _json_response({"ok": False, "error": "email and code are required."}, status=400)
        return _render_auth(
            request,
            auth_tab="signup",
            signup_stage="verify",
            signup_email=email or "",
            auth_error="ایمیل و کد الزامی است.",
            status=400,
        )

    ok, error, status_code = _verify_code(email, code)
    if not ok:
        if _wants_json(request):
            return _json_response({"ok": False, "error": error}, status=status_code)
        return _render_auth(
            request,
            auth_tab="signup",
            signup_stage="verify",
            signup_email=email,
            auth_error=error,
            status=status_code,
        )

    _set_signup_pending(request, email=email)

    if _wants_json(request):
        return _json_response({"ok": True, "pending_signup": True, "email": email})

    next_url = _safe_next_url(request)
    complete_url = f"{reverse('accounts:register')}?stage=complete&email={email}&next={next_url}"
    return redirect(complete_url)


@require_POST
def complete_signup_view(request):
    payload = _parse_payload(request)

    email = _validate_email_field(payload.get("email", ""))
    first_name = (payload.get("first_name") or "").strip()
    password = payload.get("password") or ""
    password_confirm = payload.get("password_confirm") or ""

    if not email or not first_name or not password or not password_confirm:
        if _wants_json(request):
            return _json_response({"ok": False, "error": "All fields are required."}, status=400)
        return _render_auth(
            request,
            auth_tab="signup",
            signup_stage="complete",
            signup_email=email or "",
            auth_error="همه فیلدها الزامی هستند.",
            status=400,
        )

    pending_email = _get_signup_pending_email(request)
    if not pending_email or pending_email != email:
        if _wants_json(request):
            return _json_response({"ok": False, "error": "Signup session is invalid or expired."}, status=403)
        return _render_auth(
            request,
            auth_tab="signup",
            signup_stage="request",
            signup_email=email,
            auth_error="جلسه ثبت‌نام منقضی شده است. دوباره کد بگیرید.",
            status=403,
        )

    if password != password_confirm:
        if _wants_json(request):
            return _json_response({"ok": False, "error": "Passwords do not match."}, status=400)
        return _render_auth(
            request,
            auth_tab="signup",
            signup_stage="complete",
            signup_email=email,
            auth_error="رمز عبور و تکرار آن یکسان نیستند.",
            status=400,
        )

    user_model = get_user_model()
    user = user_model.objects.filter(email__iexact=email).first()

    if user and user.has_usable_password():
        if _wants_json(request):
            return _json_response({"ok": False, "error": "Account already exists. Please login."}, status=409)
        return _render_auth(
            request,
            auth_tab="login",
            signup_stage="request",
            login_email=email,
            auth_error="این ایمیل قبلاً ثبت شده است. وارد شوید.",
            status=409,
        )

    if not user:
        username = _build_unique_username(email)
        user = user_model.objects.create_user(username=username, email=email)

    user.first_name = first_name

    try:
        validate_password(password, user=user)
    except ValidationError as exc:
        if _wants_json(request):
            return _json_response({"ok": False, "error": " ".join(exc.messages)}, status=400)
        return _render_auth(
            request,
            auth_tab="signup",
            signup_stage="complete",
            signup_email=email,
            auth_error=" ".join(exc.messages),
            status=400,
        )

    user.set_password(password)
    user.save(update_fields=["first_name", "password", "email", "username"])
    UserProfile.objects.get_or_create(user=user)

    _clear_signup_pending(request)
    login(request, user)

    next_url = _safe_next_url(request)

    if _wants_json(request):
        return _json_response({"ok": True, "user": {"id": user.id, "email": user.email}, "next": next_url})

    return redirect(next_url)


@require_POST
def login_password_view(request):
    payload = _parse_payload(request)
    email = _validate_email_field(payload.get("email", ""))
    password = payload.get("password") or ""

    if not email or not password:
        if _wants_json(request):
            return _json_response({"ok": False, "error": "email and password are required."}, status=400)
        return _render_auth(
            request,
            auth_tab="login",
            signup_stage="request",
            login_email=email or "",
            auth_error="ایمیل و رمز عبور الزامی است.",
            status=400,
        )

    user_model = get_user_model()
    candidate = user_model.objects.filter(email__iexact=email).first()
    if not candidate:
        if _wants_json(request):
            return _json_response({"ok": False, "error": "Invalid credentials."}, status=400)
        return _render_auth(
            request,
            auth_tab="login",
            signup_stage="request",
            login_email=email,
            auth_error="اطلاعات ورود نادرست است.",
            status=400,
        )

    user = authenticate(request, username=candidate.get_username(), password=password)
    if not user:
        if _wants_json(request):
            return _json_response({"ok": False, "error": "Invalid credentials."}, status=400)
        return _render_auth(
            request,
            auth_tab="login",
            signup_stage="request",
            login_email=email,
            auth_error="اطلاعات ورود نادرست است.",
            status=400,
        )

    login(request, user)
    next_url = _safe_next_url(request)

    if _wants_json(request):
        return _json_response({"ok": True, "user": {"id": user.id, "email": user.email}, "next": next_url})
    return redirect(next_url)


@require_POST
def logout_view(request):
    logout(request)
    if _wants_json(request):
        return _json_response({"ok": True})
    return redirect("core:home")


@require_POST
def resend_code_view(request):
    payload = _parse_payload(request)
    email = _validate_email_field(payload.get("email", ""))
    if not email:
        if _wants_json(request):
            return _json_response({"ok": False, "error": "A valid email is required."}, status=400)
        return _render_auth(
            request,
            auth_tab="signup",
            signup_stage="verify",
            signup_email="",
            auth_error="ایمیل معتبر وارد کنید.",
            status=400,
        )

    ok, error, status_code = _send_code(email, request)
    if not ok:
        if _wants_json(request):
            return _json_response({"ok": False, "error": error}, status=status_code)
        return _render_auth(
            request,
            auth_tab="signup",
            signup_stage="verify",
            signup_email=email,
            auth_error=error,
            status=status_code,
        )

    if _wants_json(request):
        return _json_response({"ok": True, "message": "Verification code resent."})
    return _render_auth(
        request,
        auth_tab="signup",
        signup_stage="verify",
        signup_email=email,
        auth_success="کد تایید مجددا ارسال شد.",
    )


@login_required
def profile_view(request):
    context = {
        "active_nav": "profile",
        "seo": build_seo_context(request, page_type="profile"),
    }
    return render(request, "pages/profile.html", context)
