from __future__ import annotations
from django.db import models
from django.urls import reverse


class Category(models.Model):
    title = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, allow_unicode=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
    )
    description = models.TextField(blank=True)
    seo_title = models.CharField(max_length=180, blank=True)
    seo_description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_indexable = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "title"]
        indexes = [
            models.Index(fields=["is_active"]),
            models.Index(fields=["is_indexable"]),
        ]

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("taxonomy:category_detail", kwargs={"category_slug": self.slug})


class Tag(models.Model):
    title = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, allow_unicode=True)
    description = models.TextField(blank=True)
    seo_title = models.CharField(max_length=180, blank=True)
    seo_description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_indexable = models.BooleanField(default=False)

    class Meta:
        ordering = ["title"]
        indexes = [
            models.Index(fields=["is_active"]),
            models.Index(fields=["is_indexable"]),
        ]

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("taxonomy:tag_detail", kwargs={"tag_slug": self.slug})
