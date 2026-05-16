from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.content.models import Article
from apps.taxonomy.models import Category, Tag


class PromptTemplate(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"
    STATUS_ARCHIVED = "archived"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PUBLISHED, "Published"),
        (STATUS_ARCHIVED, "Archived"),
    ]

    key = models.SlugField(
        max_length=80,
        unique=True,
        allow_unicode=True,
        verbose_name="کلید",
        help_text="کلید ثابت برای ارجاع (مثلاً: markdown-superprompt)",
    )
    title = models.CharField(max_length=200, verbose_name="عنوان")
    description = models.TextField(blank=True, verbose_name="توضیح کوتاه")

    # Markdown / plain text (usually includes fenced code)
    body = models.TextField(verbose_name="متن پرامپت")

    language = models.CharField(max_length=10, default="fa", verbose_name="زبان")
    status = models.CharField(
        max_length=12,
        choices=STATUS_CHOICES,
        default=STATUS_PUBLISHED,
        verbose_name="وضعیت",
    )
    is_active = models.BooleanField(default=True, verbose_name="فعال")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_prompt_templates",
        verbose_name="ایجادکننده",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_prompt_templates",
        verbose_name="آخرین ویرایش توسط",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاریخ ویرایش")

    class Meta:
        ordering = ["title"]
        indexes = [
            models.Index(fields=["key"], name="editorial_pr_key_idx"),
            models.Index(fields=["status", "is_active"], name="editorial_pr_state_idx"),
            models.Index(fields=["-updated_at"], name="editorial_pr_updated_idx"),
        ]
        verbose_name = "پرامپت"
        verbose_name_plural = "پرامپت‌ها"

    def __str__(self) -> str:
        return f"{self.title} ({self.key})"


class WritingRuleSet(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"
    STATUS_ARCHIVED = "archived"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PUBLISHED, "Published"),
        (STATUS_ARCHIVED, "Archived"),
    ]

    key = models.SlugField(
        max_length=80,
        unique=True,
        allow_unicode=True,
        verbose_name="کلید",
        help_text="کلید ثابت (مثلاً: educational-article-rules)",
    )
    title = models.CharField(max_length=200, verbose_name="عنوان")
    description = models.TextField(blank=True, verbose_name="توضیح کوتاه")

    # Markdown rules/checklist
    body = models.TextField(verbose_name="قوانین/راهنما")

    # Free-form scenario code: educational / analysis / howto / breaking ...
    scenario = models.CharField(
        max_length=50,
        blank=True,
        db_index=True,
        verbose_name="سناریو",
        help_text="مثال: educational, analysis, howto ...",
    )

    # Limit to specific content types (empty means all)
    applies_to_content_types = models.JSONField(
        default=list,
        blank=True,
        verbose_name="محدود به نوع محتوا",
        help_text='لیست مانند: ["short_news","post","article"] (خالی یعنی همه)',
    )

    categories = models.ManyToManyField(
        Category,
        blank=True,
        related_name="writing_rules",
        verbose_name="دسته‌ها",
    )
    tags = models.ManyToManyField(
        Tag,
        blank=True,
        related_name="writing_rules",
        verbose_name="تگ‌ها",
    )

    default_prompt = models.ForeignKey(
        PromptTemplate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="default_for_rulesets",
        verbose_name="پرامپت پیشنهادی",
    )
    prompts = models.ManyToManyField(
        PromptTemplate,
        blank=True,
        related_name="rule_sets",
        verbose_name="پرامپت‌های مرتبط",
    )

    priority = models.PositiveSmallIntegerField(
        default=100,
        verbose_name="اولویت",
        help_text="عدد کمتر = پیشنهاد بالاتر در لیست",
    )

    status = models.CharField(
        max_length=12,
        choices=STATUS_CHOICES,
        default=STATUS_PUBLISHED,
        verbose_name="وضعیت",
    )
    is_active = models.BooleanField(default=True, verbose_name="فعال")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_writing_rules",
        verbose_name="ایجادکننده",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_writing_rules",
        verbose_name="آخرین ویرایش توسط",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاریخ ویرایش")

    class Meta:
        ordering = ["priority", "title"]
        indexes = [
            models.Index(fields=["key"], name="editorial_wr_key_idx"),
            models.Index(fields=["scenario", "status", "is_active"], name="editorial_wr_state_idx"),
            models.Index(fields=["-updated_at"], name="editorial_wr_updated_idx"),
        ]
        verbose_name = "قانون/راهنما"
        verbose_name_plural = "قوانین/راهنماها"

    def __str__(self) -> str:
        return f"{self.title} ({self.key})"

    def clean(self):
        super().clean()
        allowed = {Article.CONTENT_SHORT_NEWS, Article.CONTENT_POST, Article.CONTENT_ARTICLE}
        bad = [x for x in (self.applies_to_content_types or []) if x not in allowed]
        if bad:
            raise ValidationError(
                {
                    "applies_to_content_types": (
                        f"Invalid content types: {bad}. Allowed: {sorted(allowed)}"
                    )
                }
            )
