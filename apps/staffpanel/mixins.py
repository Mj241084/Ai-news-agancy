from __future__ import annotations
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpResponseForbidden


GROUP_CONTENT_EDITORS = "content_editors"
GROUP_EDITORIAL_ADMINS = "editorial_admins"


def user_in_group(user, group_name: str) -> bool:
    """Return True if the user is in the given group (superusers always pass)."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name=group_name).exists()


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Allow access only for authenticated staff users."""

    login_url = settings.LOGIN_URL
    raise_exception = False

    def test_func(self):
        return bool(self.request.user and self.request.user.is_staff)

    def handle_no_permission(self):
        if self.request.user.is_authenticated and not self.request.user.is_staff:
            return HttpResponseForbidden("دسترسی استاف لازم است.")
        return super().handle_no_permission()


class ContentEditorRequiredMixin(StaffRequiredMixin):
    """Staff users that can create/edit content and manage tags/entities."""

    def test_func(self):
        user = self.request.user
        return bool(
            user
            and user.is_staff
            and (
                user_in_group(user, GROUP_EDITORIAL_ADMINS)
                or user_in_group(user, GROUP_CONTENT_EDITORS)
            )
        )

    def handle_no_permission(self):
        if self.request.user.is_authenticated and self.request.user.is_staff:
            return HttpResponseForbidden("دسترسی استاف کافی نیست.")
        return super().handle_no_permission()


class EditorialAdminRequiredMixin(StaffRequiredMixin):
    """Staff users with full access (including categories and prompts/rules CRUD)."""

    def test_func(self):
        user = self.request.user
        return bool(user and user.is_staff and user_in_group(user, GROUP_EDITORIAL_ADMINS))

    def handle_no_permission(self):
        if self.request.user.is_authenticated and self.request.user.is_staff:
            return HttpResponseForbidden("دسترسی استاف کافی نیست.")
        return super().handle_no_permission()


class SuperuserRequiredMixin(StaffRequiredMixin):
    """Restrict access to Django superusers only (still requires is_staff)."""

    def test_func(self):
        user = self.request.user
        return bool(user and user.is_staff and user.is_superuser)
