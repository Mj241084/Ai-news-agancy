from __future__ import annotations
from django.db import models

from apps.content.models import Article
from apps.relations.utils import normalize_article_pair


class ArticleRelation(models.Model):
    article_a = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name="relations_as_primary",
    )
    article_b = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name="relations_as_secondary",
    )
    score = models.FloatField()
    signals = models.JSONField(default=dict, blank=True)
    algo_version = models.CharField(max_length=40, default="v1")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["article_a", "article_b"], name="uniq_article_relation_pair"),
            models.CheckConstraint(
                check=~models.Q(article_a=models.F("article_b")),
                name="article_relation_no_self_link",
            ),
        ]
        indexes = [
            models.Index(fields=["article_a", "-score"]),
            models.Index(fields=["article_b", "-score"]),
            models.Index(fields=["-score"]),
        ]

    def save(self, *args, **kwargs):
        if self.article_a_id and self.article_b_id:
            self.article_a_id, self.article_b_id = normalize_article_pair(
                self.article_a_id,
                self.article_b_id,
            )
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.article_a_id}<->{self.article_b_id} ({self.score})"
