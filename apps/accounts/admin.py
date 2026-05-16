from __future__ import annotations
from django.contrib import admin

from apps.accounts.models import EmailOTP, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "updated_at")
    search_fields = ("user__username", "user__email")


@admin.register(EmailOTP)
class EmailOTPAdmin(admin.ModelAdmin):
    list_display = ("email", "created_at", "expires_at", "used_at", "attempt_count")
    search_fields = ("email",)
    list_filter = ("created_at", "expires_at", "used_at")
