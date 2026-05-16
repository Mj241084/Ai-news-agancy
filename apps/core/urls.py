from __future__ import annotations
from django.urls import path

from apps.core import views

app_name = "core"

urlpatterns = [
    path("", views.home_view, name="home"),
    path("robots.txt", views.robots_txt_view, name="robots_txt"),
    path("search/", views.search_view, name="search"),
    path("popular/", views.popular_view, name="popular"),
    path("team-picks/", views.team_picks_view, name="team_picks"),
    path("about/", views.about_view, name="about"),
    path("contact/", views.contact_view, name="contact"),
    path("terms/", views.terms_view, name="terms"),
    path("privacy/", views.privacy_view, name="privacy"),
]
