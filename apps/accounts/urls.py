from __future__ import annotations
from django.urls import path

from apps.accounts import views

app_name = "accounts"

urlpatterns = [
    path("auth/register/", views.register_view, name="register"),
    path("auth/login/", views.login_view, name="login"),
    path("auth/verify/", views.verify_email_view, name="verify_email"),
    path("auth/logout/", views.logout_view, name="logout"),
    path("auth/request-code/", views.request_code_view, name="request_code"),
    path("auth/verify-code/", views.verify_code_view, name="verify_code"),
    path("auth/complete-signup/", views.complete_signup_view, name="complete_signup"),
    path("auth/login-password/", views.login_password_view, name="login_password"),
    path("auth/resend-code/", views.resend_code_view, name="resend_code"),
    path("profile/", views.profile_view, name="profile"),
]
