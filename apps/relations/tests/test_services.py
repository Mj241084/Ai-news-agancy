from __future__ import annotations
from django.test import TestCase
from django.utils import timezone

from apps.content.models import Article, ArticleEntity, ArticleTag
from apps.entities.models import Entity
from apps.relations.services import build_relations_for_article, normalize_title_tokens
from apps.taxonomy.models import Tag


class RelationServiceTests(TestCase):
    def _make_article(self, *, title: str, slug: str) -> Article:
        return Article.objects.create(
            title=title,
            slug=slug,
            body="body",
            excerpt="excerpt",
            content_type=Article.CONTENT_ARTICLE,
            status=Article.STATUS_PUBLISHED,
            published_at=timezone.now(),
        )

    def test_normalize_title_tokens_is_deterministic(self):
        text_a = "تصوير ساز هوش مصنوعى و AI"
        text_b = "تصویر   سازِ هوش مصنوعی AI"

        tokens_a = normalize_title_tokens(text_a)
        tokens_b = normalize_title_tokens(text_b)

        self.assertEqual(tokens_a, tokens_b)
        self.assertIn("تصویر_ساز", tokens_a)

    def test_entity_overlap_scores_higher_than_tag_only_overlap(self):
        source = self._make_article(title="Source Article", slug="src-article")
        candidate_entity = self._make_article(title="Entity Match", slug="entity-match")
        candidate_tag = self._make_article(title="Tag Match", slug="tag-match")

        shared_entity = Entity.objects.create(type=Entity.TYPE_COMPANY, name="OpenAI", slug="openai")
        shared_tag = Tag.objects.create(title="Agents", slug="agents")

        ArticleEntity.objects.create(article=source, entity=shared_entity, role=ArticleEntity.ROLE_MAIN, importance=1.0)
        ArticleEntity.objects.create(article=candidate_entity, entity=shared_entity, role=ArticleEntity.ROLE_MAIN, importance=1.0)

        ArticleTag.objects.create(article=source, tag=shared_tag)
        ArticleTag.objects.create(article=candidate_tag, tag=shared_tag)

        rows = build_relations_for_article(source.id, top_n=10, max_candidates=100, horizon_days=365, algo_version="v1")
        scores_by_slug = {row["slug"]: row["score"] for row in rows}

        self.assertIn("entity-match", scores_by_slug)
        self.assertIn("tag-match", scores_by_slug)
        self.assertGreater(scores_by_slug["entity-match"], scores_by_slug["tag-match"])
