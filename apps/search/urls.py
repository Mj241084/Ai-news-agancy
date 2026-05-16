from __future__ import annotations
from django.urls import path

from apps.search.views import search_api_view

app_name = "search"

urlpatterns = [
    path("api/search/", search_api_view, name="search_api"),
]
