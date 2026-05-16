from __future__ import annotations
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.content.models import Article
from apps.interactions.models import DailyArticleInteraction
from apps.personalization.services import compute_daily_interest_for_user, compute_daily_recommendations


class PersonalizationServiceTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="puser", email="puser@example.com")
        self.today = timezone.localdate()

    def _make_article(self, *, title: str, slug: str, is_team_pick: bool = False) -> Article:
        return Article.objects.create(
            title=title,
            slug=slug,
            body="body",
            excerpt="excerpt",
            content_type=Article.CONTENT_ARTICLE,
            status=Article.STATUS_PUBLISHED,
            published_at=timezone.now(),
            is_team_pick=is_team_pick,
        )

    def test_interest_profile_weights_like_share_more_than_view(self):
        article_view = self._make_article(title="View heavy", slug="view-heavy")
        article_share = self._make_article(title="Share heavy", slug="share-heavy")

        DailyArticleInteraction.objects.create(
            date=self.today,
            user=self.user,
            article=article_view,
            views=8,
        )
        DailyArticleInteraction.objects.create(
            date=self.today,
            user=self.user,
            article=article_share,
            shares=2,
        )

        profile = compute_daily_interest_for_user(self.user, self.today, algo_version="v1")
        seed_scores = {item["slug"]: item["score"] for item in profile["seed_articles"]}

        self.assertGreater(seed_scores["share-heavy"], seed_scores["view-heavy"])

    def test_recommendations_exclude_seen_and_include_team_pick_fallback(self):
        seen_article = self._make_article(title="Seen", slug="seen-article")
        team_pick_article = self._make_article(title="Team Pick", slug="team-pick", is_team_pick=True)
        self._make_article(title="Latest", slug="latest-article")

        DailyArticleInteraction.objects.create(
            date=self.today,
            user=self.user,
            article=seen_article,
            views=1,
        )

        empty_interest_profile = {
            "algo_version": "v1",
            "date": self.today.isoformat(),
            "window_days": 30,
            "actor": {"type": "user", "id": self.user.id},
            "top_categories": [],
            "top_entities": [],
            "top_tags": [],
            "seed_articles": [],
        }

        recs = compute_daily_recommendations(
            empty_interest_profile,
            self.today,
            actor=self.user,
            algo_version="v1",
        )
        rec_slugs = [item["slug"] for item in recs]

        self.assertNotIn("seen-article", rec_slugs)
        self.assertIn(team_pick_article.slug, rec_slugs)
