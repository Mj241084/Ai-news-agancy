from __future__ import annotations
from django.urls import path

from apps.interactions import views

app_name = "interactions"

urlpatterns = [
    path("ajax/polls/active/", views.ajax_active_poll_view, name="ajax_active_poll"),
    path("ajax/polls/submit/", views.ajax_submit_poll_view, name="ajax_submit_poll"),
]
