from __future__ import annotations
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from apps.content.models import Article


class Visitor(models.Model):
    anon_id = models.CharField(max_length=36, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="visitors",
    )
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True, db_index=True)

    def __str__(self) -> str:
        return self.anon_id


class DailyArticleInteraction(models.Model):
    date = models.DateField(db_index=True)
    visitor = models.ForeignKey(
        Visitor,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="daily_article_interactions",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="daily_article_interactions",
    )
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name="daily_interactions",
    )

    views = models.PositiveIntegerField(default=0)
    clicks = models.PositiveIntegerField(default=0)
    likes = models.PositiveIntegerField(default=0)
    shares = models.PositiveIntegerField(default=0)
    bookmarks = models.PositiveIntegerField(default=0)
    dwell_seconds = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    (Q(user__isnull=False) & Q(visitor__isnull=True))
                    | (Q(user__isnull=True) & Q(visitor__isnull=False))
                ),
                name="interaction_user_xor_visitor",
            ),
            models.UniqueConstraint(
                fields=["date", "visitor", "article"],
                name="uniq_daily_interaction_visitor",
            ),
            models.UniqueConstraint(
                fields=["date", "user", "article"],
                name="uniq_daily_interaction_user",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "date"]),
            models.Index(fields=["visitor", "date"]),
            models.Index(fields=["article", "date"]),
        ]

    def __str__(self) -> str:
        actor = self.user_id or self.visitor_id
        return f"{self.date} :: {actor} :: {self.article_id}"


class UserArticleState(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="article_states",
    )
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name="user_states",
    )
    liked_at = models.DateTimeField(null=True, blank=True, db_index=True)
    bookmarked_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "article"], name="uniq_user_article_state"),
        ]
        indexes = [
            models.Index(fields=["user", "liked_at"]),
            models.Index(fields=["user", "bookmarked_at"]),
            models.Index(fields=["article", "liked_at"]),
            models.Index(fields=["article", "bookmarked_at"]),
        ]

    def __str__(self) -> str:
        return f"State<{self.user_id}:{self.article_id}>"



class ArticleRating(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="ratings")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="article_ratings",
    )
    visitor = models.ForeignKey(
        "interactions.Visitor",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="article_ratings",
    )
    value = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    (Q(user__isnull=False) & Q(visitor__isnull=True))
                    | (Q(user__isnull=True) & Q(visitor__isnull=False))
                ),
                name="article_rating_user_xor_visitor",
            ),
            models.UniqueConstraint(
                fields=["article", "user"],
                condition=Q(user__isnull=False),
                name="uniq_article_rating_user",
            ),
            models.UniqueConstraint(
                fields=["article", "visitor"],
                condition=Q(visitor__isnull=False),
                name="uniq_article_rating_visitor",
            ),
        ]
        indexes = [
            models.Index(fields=["article", "created_at"]),
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["visitor", "created_at"]),
        ]

    def __str__(self) -> str:
        actor = self.user_id or self.visitor_id
        return f"Rating<{self.article_id}:{actor}:{self.value}>"

class Poll(models.Model):
    title = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=False, db_index=True)
    starts_at = models.DateTimeField(null=True, blank=True, db_index=True)
    ends_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["is_active", "starts_at", "ends_at"]),
        ]

    def __str__(self) -> str:
        return self.title or f"Poll #{self.pk or '-'}"


class PollQuestion(models.Model):
    KIND_SINGLE = "single"
    KIND_MULTI = "multi"
    KIND_CHOICES = [
        (KIND_SINGLE, "Single"),
        (KIND_MULTI, "Multi"),
    ]

    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="questions")
    text = models.TextField()
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=KIND_SINGLE)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        indexes = [
            models.Index(fields=["poll", "sort_order"]),
        ]

    def __str__(self) -> str:
        return f"Q{self.pk or '-'}@P{self.poll_id}"


class PollChoice(models.Model):
    question = models.ForeignKey(PollQuestion, on_delete=models.CASCADE, related_name="choices")
    text = models.CharField(max_length=255)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        indexes = [
            models.Index(fields=["question", "sort_order"]),
        ]

    def __str__(self) -> str:
        return f"C{self.pk or '-'}@Q{self.question_id}"


class PollResponse(models.Model):
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="responses")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="poll_responses",
    )
    visitor = models.ForeignKey(
        Visitor,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="poll_responses",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    (Q(user__isnull=False) & Q(visitor__isnull=True))
                    | (Q(user__isnull=True) & Q(visitor__isnull=False))
                ),
                name="poll_response_user_xor_visitor",
            ),
            models.UniqueConstraint(
                fields=["poll", "user"],
                condition=Q(user__isnull=False),
                name="uniq_poll_response_user",
            ),
            models.UniqueConstraint(
                fields=["poll", "visitor"],
                condition=Q(visitor__isnull=False),
                name="uniq_poll_response_visitor",
            ),
        ]
        indexes = [
            models.Index(fields=["poll", "created_at"]),
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["visitor", "created_at"]),
        ]

    def __str__(self) -> str:
        actor = self.user_id or self.visitor_id
        return f"PollResponse<{self.poll_id}:{actor}>"


class PollAnswer(models.Model):
    response = models.ForeignKey(PollResponse, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(PollQuestion, on_delete=models.CASCADE, related_name="answers")
    choice = models.ForeignKey(PollChoice, on_delete=models.CASCADE, related_name="answers")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["response", "choice"], name="uniq_poll_answer_response_choice"),
        ]
        indexes = [
            models.Index(fields=["response", "question"]),
            models.Index(fields=["question", "choice"]),
        ]

    def clean(self):
        errors = {}

        if self.response_id and self.question_id and self.response.poll_id != self.question.poll_id:
            errors["question"] = "Question does not belong to the same poll."

        if self.choice_id and self.question_id and self.choice.question_id != self.question_id:
            errors["choice"] = "Choice does not belong to this question."

        if self.response_id and self.question_id and self.question.kind == PollQuestion.KIND_SINGLE:
            existing = PollAnswer.objects.filter(response_id=self.response_id, question_id=self.question_id)
            if self.pk:
                existing = existing.exclude(pk=self.pk)
            if existing.exists():
                errors["question"] = "Single-choice question can only have one choice."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Answer<R{self.response_id}:Q{self.question_id}:C{self.choice_id}>"
