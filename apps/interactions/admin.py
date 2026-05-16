from __future__ import annotations
from django.contrib import admin

from apps.interactions.models import (
    DailyArticleInteraction,
    ArticleRating,
    Poll,
    PollAnswer,
    PollChoice,
    PollQuestion,
    PollResponse,
    UserArticleState,
    Visitor,
)


@admin.register(Visitor)
class VisitorAdmin(admin.ModelAdmin):
    list_display = ("anon_id", "user", "first_seen", "last_seen")
    search_fields = ("anon_id", "user__username", "user__email")
    list_filter = ("last_seen",)


@admin.register(DailyArticleInteraction)
class DailyArticleInteractionAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "user",
        "visitor",
        "article",
        "views",
        "clicks",
        "likes",
        "shares",
        "bookmarks",
        "dwell_seconds",
    )
    list_filter = ("date",)
    search_fields = ("article__title", "user__username", "visitor__anon_id")


@admin.register(UserArticleState)
class UserArticleStateAdmin(admin.ModelAdmin):
    list_display = ("user", "article", "liked_at", "bookmarked_at", "updated_at")
    list_filter = ("liked_at", "bookmarked_at")
    search_fields = ("user__username", "user__email", "article__title", "article__slug")


@admin.register(ArticleRating)
class ArticleRatingAdmin(admin.ModelAdmin):
    list_display = ("article", "value", "user", "visitor", "created_at", "updated_at")
    list_filter = ("value", "created_at")
    search_fields = ("article__title", "article__slug", "user__username", "user__email", "visitor__anon_id")


class PollChoiceInline(admin.TabularInline):
    model = PollChoice
    extra = 0


class PollQuestionInline(admin.StackedInline):
    model = PollQuestion
    extra = 0
    show_change_link = True


@admin.register(Poll)
class PollAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "is_active", "starts_at", "ends_at", "created_at")
    list_filter = ("is_active",)
    search_fields = ("title",)
    inlines = [PollQuestionInline]


@admin.register(PollQuestion)
class PollQuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "poll", "kind", "sort_order")
    list_filter = ("kind",)
    search_fields = ("text", "poll__title")
    inlines = [PollChoiceInline]


@admin.register(PollResponse)
class PollResponseAdmin(admin.ModelAdmin):
    list_display = ("id", "poll", "user", "visitor", "created_at")
    list_filter = ("poll",)
    search_fields = ("poll__title", "user__username", "visitor__anon_id")


@admin.register(PollAnswer)
class PollAnswerAdmin(admin.ModelAdmin):
    list_display = ("id", "response", "question", "choice")
    list_filter = ("question",)
