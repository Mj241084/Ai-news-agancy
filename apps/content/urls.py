from __future__ import annotations
from django.urls import path

from apps.content import views

app_name = "content"

urlpatterns = [
    path("p/<slug:slug>/", views.detail_view, name="detail"),
    path("articles/", views.article_list_view, name="article_list"),
    path("news/", views.news_list_view, name="news_list"),
    path("ajax/p/<slug:slug>/stats/", views.ajax_stats_view, name="ajax_stats"),
    path("ajax/p/<slug:slug>/comments/", views.ajax_comments_view, name="ajax_comments"),
    path("ajax/p/<slug:slug>/related/", views.ajax_related_view, name="ajax_related"),
    path("ajax/p/<slug:slug>/actions/", views.ajax_actions_view, name="ajax_actions"),
]
