from __future__ import annotations
from django.urls import path

from apps.entities import views

app_name = "entities"

urlpatterns = [
    path("entity/<str:entity_type>/<slug:slug>/", views.entity_detail_view, name="detail"),
]
