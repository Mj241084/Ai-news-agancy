from __future__ import annotations
from django.db import models
from django.urls import reverse


class Entity(models.Model):
    TYPE_COMPANY = "company"
    TYPE_PERSON = "person"
    TYPE_MODEL = "model"
    TYPE_PRODUCT = "product"
    TYPE_LAB = "lab"
    TYPE_DATASET = "dataset"
    TYPE_OTHER = "other"

    TYPE_CHOICES = [
        (TYPE_COMPANY, "Company"),
        (TYPE_PERSON, "Person"),
        (TYPE_MODEL, "Model"),
        (TYPE_PRODUCT, "Product"),
        (TYPE_LAB, "Lab"),
        (TYPE_DATASET, "Dataset"),
        (TYPE_OTHER, "Other"),
    ]

    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True, allow_unicode=True)
    aliases = models.JSONField(default=list, blank=True)
    description = models.TextField(blank=True)
    seo_title = models.CharField(max_length=180, blank=True)
    seo_description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_indexable = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["type", "name"], name="uniq_entity_type_name"),
        ]
        indexes = [
            models.Index(fields=["type", "slug"]),
            models.Index(fields=["name"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["is_indexable"]),
        ]
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.type})"

    def get_absolute_url(self) -> str:
        return reverse("entities:detail", kwargs={"entity_type": self.type, "slug": self.slug})


class RankingList(models.Model):
    KIND_COMPANY = "company"
    KIND_MODEL = "model"
    KIND_CHOICES = [
        (KIND_COMPANY, "Company"),
        (KIND_MODEL, "Model"),
    ]

    title = models.CharField(max_length=255)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    columns = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
        indexes = [
            models.Index(fields=["is_active", "kind"]),
        ]

    def __str__(self) -> str:
        return self.title


class RankingEntry(models.Model):
    ranking = models.ForeignKey(RankingList, on_delete=models.CASCADE, related_name="entries")
    rank = models.PositiveIntegerField()
    name = models.CharField(max_length=255)
    score = models.FloatField(null=True, blank=True)
    data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["rank", "id"]
        constraints = [
            models.UniqueConstraint(fields=["ranking", "rank"], name="uniq_ranking_entry_rank"),
        ]
        indexes = [
            models.Index(fields=["ranking", "rank"]),
        ]

    def __str__(self) -> str:
        return f"{self.ranking_id}:{self.rank}:{self.name}"
