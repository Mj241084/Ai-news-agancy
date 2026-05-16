from __future__ import annotations
from django.conf import settings

from apps.interactions.services import get_or_create_visitor_from_request, touch_visitor


class VisitorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.visitor = None
        visitor = get_or_create_visitor_from_request(request)
        request.visitor = visitor
        touch_visitor(visitor)

        response = self.get_response(request)

        if getattr(request, "_visitor_set_cookie", False):
            cookie_name = getattr(settings, "VISITOR_COOKIE_NAME", "anon_id")
            cookie_age = getattr(settings, "VISITOR_COOKIE_AGE", 60 * 60 * 24 * 365)
            response.set_cookie(
                cookie_name,
                request._visitor_anon_id,
                max_age=cookie_age,
                httponly=True,
                samesite="Lax",
                secure=not settings.DEBUG,
            )

        return response
