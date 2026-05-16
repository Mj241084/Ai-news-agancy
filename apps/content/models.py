from __future__ import annotations
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.entities.models import Entity
from apps.taxonomy.models import Category, Tag


ARTICLE_GOALS_ALLOWED = {"views", "comments", "shares", "rating"}


def validate_article_goals(value):
    if value in (None, ""):
        return
    if not isinstance(value, list):
        raise ValidationError("اهداف باید به صورت لیست ذخیره شوند.")
    if len(value) != len(set(value)):
        raise ValidationError("اهداف تکراری مجاز نیست.")
    invalid = [item for item in value if item not in ARTICLE_GOALS_ALLOWED]
    if invalid:
        raise ValidationError(f"اهداف نامعتبر: {', '.join(str(x) for x in invalid)}")


class Article(models.Model):
    CONTENT_SHORT_NEWS = "short_news"
    CONTENT_POST = "post"
    CONTENT_ARTICLE = "article"

    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"

    CONTENT_TYPE_CHOICES = [
        (CONTENT_SHORT_NEWS, "Short News"),
        (CONTENT_POST, "Post"),
        (CONTENT_ARTICLE, "Article"),
    ]

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PUBLISHED, "Published"),
    ]

    GOAL_VIEWS = "views"
    GOAL_COMMENTS = "comments"
    GOAL_SHARES = "shares"
    GOAL_RATING = "rating"

    GOAL_CHOICES = [
        (GOAL_VIEWS, "Views"),
        (GOAL_COMMENTS, "Comments"),
        (GOAL_SHARES, "Shares"),
        (GOAL_RATING, "Rating"),
    ]

    content_type = models.CharField(max_length=20, choices=CONTENT_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True, allow_unicode=True)
    excerpt = models.TextField(blank=True)
    body = models.TextField()
    language = models.CharField(max_length=10, default="fa")
    hero_image = models.URLField(max_length=500, null=True, blank=True)
    thumbnail = models.URLField(max_length=500, null=True, blank=True)
    video_url = models.URLField(max_length=500, null=True, blank=True)
    video_thumbnail = models.URLField(max_length=500, null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    seo_title = models.CharField(max_length=180, blank=True)
    seo_description = models.TextField(blank=True)
    canonical_path = models.CharField(max_length=500, blank=True)
    meta_robots = models.CharField(max_length=120, blank=True)
    is_team_pick = models.BooleanField(default=False, db_index=True)
    goals = models.JSONField(default=list, blank=True, validators=[validate_article_goals])

    categories = models.ManyToManyField(Category, through="ArticleCategory", related_name="articles")
    tags = models.ManyToManyField(Tag, through="ArticleTag", related_name="articles")
    entities = models.ManyToManyField(Entity, through="ArticleEntity", related_name="articles")

    class Meta:
        ordering = ["-published_at", "-created_at"]
        indexes = [
            models.Index(fields=["status", "published_at"]),
            models.Index(fields=["content_type", "published_at"]),
        ]

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("content:detail", kwargs={"slug": self.slug})

    def save(self, *args, **kwargs):
        if self.status == self.STATUS_PUBLISHED and self.published_at is None:
            self.published_at = timezone.now()
        if self.status == self.STATUS_DRAFT and self.published_at is not None:
            self.published_at = None
        super().save(*args, **kwargs)


class ArticleComment(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="comments")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="article_comments")
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="replies")
    text = models.TextField(max_length=2000)
    is_visible = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["article", "is_visible", "created_at"]),
            models.Index(fields=["article", "parent", "is_visible", "created_at"]),
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"Comment<{self.id}> article={self.article_id} user={self.user_id}"


class ArticleCategory(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="article_categories")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="category_articles")
    is_primary = models.BooleanField(default=False)
    weight = models.FloatField(default=1.0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["article", "category"], name="uniq_article_category"),
            models.UniqueConstraint(
                fields=["article"],
                condition=Q(is_primary=True),
                name="uniq_primary_category_per_article",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.article_id}:{self.category_id}"


class ArticleTag(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="article_tags")
    tag = models.ForeignKey(Tag, on_delete=models.PROTECT, related_name="tag_articles")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["article", "tag"], name="uniq_article_tag"),
        ]

    def __str__(self) -> str:
        return f"{self.article_id}:{self.tag_id}"


class ArticleEntity(models.Model):
    ROLE_MAIN = "main"
    ROLE_MENTIONED = "mentioned"
    ROLE_AUTHOR = "author"
    ROLE_TARGET = "target"

    ROLE_CHOICES = [
        (ROLE_MAIN, "Main"),
        (ROLE_MENTIONED, "Mentioned"),
        (ROLE_AUTHOR, "Author"),
        (ROLE_TARGET, "Target"),
    ]

    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="article_entities")
    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="entity_articles")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_MENTIONED)
    importance = models.FloatField(
        default=1.0,
        validators=[MinValueValidator(0.1), MaxValueValidator(3.0)],
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["article", "entity", "role"], name="uniq_article_entity_role"),
            models.UniqueConstraint(
                fields=["article"],
                condition=Q(role="main"),
                name="uniq_main_entity_per_article",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.article_id}:{self.entity_id}:{self.role}"


class Source(models.Model):
    TYPE_OFFICIAL = "official"
    TYPE_BLOG = "blog"
    TYPE_PAPER = "paper"
    TYPE_SOCIAL = "social"
    TYPE_OTHER = "other"

    TYPE_CHOICES = [
        (TYPE_OFFICIAL, "Official"),
        (TYPE_BLOG, "Blog"),
        (TYPE_PAPER, "Paper"),
        (TYPE_SOCIAL, "Social"),
        (TYPE_OTHER, "Other"),
    ]

    name = models.CharField(max_length=200)
    url = models.URLField()
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_OTHER)
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=["is_active"]),
            models.Index(fields=["type"]),
        ]
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class ArticleSource(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="article_sources")
    source = models.ForeignKey(Source, on_delete=models.PROTECT, related_name="source_articles")
    original_url = models.URLField()
    note = models.TextField(blank=True)
    confidence = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["article", "source", "original_url"],
                name="uniq_article_source_url",
            )
        ]

    def __str__(self) -> str:
        return f"{self.article_id}:{self.source_id}"
