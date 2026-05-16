from __future__ import annotations
from django.urls import path

from apps.taxonomy import views

app_name = "taxonomy"

urlpatterns = [
    path("categories/", views.category_index_view, name="category_index"),
    path("c/<slug:category_slug>/", views.category_detail_view, name="category_detail"),
    path("tag/<slug:tag_slug>/", views.tag_detail_view, name="tag_detail"),
]
