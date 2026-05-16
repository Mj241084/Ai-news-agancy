from __future__ import annotations
import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.content.cache_keys import core_home_key, core_popular_key
from apps.content.models import Article, ArticleComment
from apps.interactions.models import ArticleRating, DailyArticleInteraction


class ContentAjaxFeatureTests(TestCase):
    def setUp(self):
        cache.clear()
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="ajax-user",
            email="ajax@example.com",
            password="secret12345",
        )
        self.article = Article.objects.create(
            title="Ajax Article",
            slug="ajax-article",
            excerpt="excerpt",
            body="body",
            content_type=Article.CONTENT_ARTICLE,
            status=Article.STATUS_PUBLISHED,
            published_at=timezone.now(),
        )
        self.actions_url = reverse("content:ajax_actions", args=[self.article.slug])
        self.comments_url = reverse("content:ajax_comments", args=[self.article.slug])
        self.stats_url = reverse("content:ajax_stats", args=[self.article.slug])

    def _json_post(self, url: str, payload: dict):
        return self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_guest_can_rate_article(self):
        response = self._json_post(self.actions_url, {"event": "rating", "value": 4})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["value"], 4)

        self.assertEqual(ArticleRating.objects.filter(article=self.article).count(), 1)

        stats_data = self.client.get(self.stats_url).json()
        self.assertEqual(stats_data["rating_count"], 1)
        self.assertGreater(stats_data["rating_avg"], 0)

    def test_authenticated_user_can_post_comment_reply_and_fetch_thread(self):
        self.client.force_login(self.user)

        parent_resp = self._json_post(self.comments_url, {"text": "نظر اصلی"})
        self.assertEqual(parent_resp.status_code, 200)
        parent_id = parent_resp.json()["comment"]["id"]

        reply_resp = self._json_post(self.comments_url, {"text": "پاسخ", "parent_id": parent_id})
        self.assertEqual(reply_resp.status_code, 200)
        self.assertTrue(reply_resp.json()["ok"])

        list_payload = self.client.get(self.comments_url).json()
        self.assertEqual(list_payload["total"], 2)
        self.assertEqual(len(list_payload["comments"]), 1)
        self.assertEqual(len(list_payload["comments"][0]["replies"]), 1)
        self.assertIn("پاسخ", list_payload["comments"][0]["replies"][0]["text"])

    def test_comments_pagination_uses_top_level_comments(self):
        self.client.force_login(self.user)
        for i in range(25):
            ArticleComment.objects.create(article=self.article, user=self.user, text=f"نظر {i}")

        page1 = self.client.get(self.comments_url).json()
        self.assertEqual(page1["top_level_total"], 25)
        self.assertEqual(page1["total"], 25)
        self.assertEqual(page1["page"], 1)
        self.assertTrue(page1["has_next"])
        self.assertEqual(len(page1["comments"]), 20)

        page2 = self.client.get(self.comments_url + "?page=2").json()
        self.assertEqual(page2["page"], 2)
        self.assertFalse(page2["has_next"])
        self.assertEqual(len(page2["comments"]), 5)

    def test_comment_with_blocked_word_is_rejected_after_normalization(self):
        self.client.force_login(self.user)

        for bad_text in ("این کامنت ک.یر دارد", "این کامنت کiر دارد"):
            with self.subTest(text=bad_text):
                response = self._json_post(self.comments_url, {"text": bad_text})
                self.assertEqual(response.status_code, 400)
                payload = response.json()
                self.assertFalse(payload["ok"])
                self.assertEqual(payload["error"], "لطفا از استفاده از کلمات نامناسب خودداری کنید.")

        self.assertEqual(ArticleComment.objects.filter(article=self.article).count(), 0)

    def test_view_is_deduped_for_30_minutes_and_does_not_invalidate_home_popular_cache(self):
        home_key = core_home_key(page=1)
        popular_key = core_popular_key(page=1)
        cache.set(home_key, {"cached": "home"}, timeout=300)
        cache.set(popular_key, {"cached": "popular"}, timeout=300)

        first = self._json_post(self.actions_url, {"event": "view"})
        second = self._json_post(self.actions_url, {"event": "view"})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)

        interaction = DailyArticleInteraction.objects.get(article=self.article)
        self.assertEqual(interaction.views, 1)

        self.assertIsNotNone(cache.get(home_key))
        self.assertIsNotNone(cache.get(popular_key))

    def test_rating_invalidates_home_and_popular_cache(self):
        home_key = core_home_key(page=1)
        popular_key = core_popular_key(page=1)
        cache.set(home_key, {"cached": "home"}, timeout=300)
        cache.set(popular_key, {"cached": "popular"}, timeout=300)

        response = self._json_post(self.actions_url, {"event": "rating", "value": 5})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])

        self.assertIsNone(cache.get(home_key))
        self.assertIsNone(cache.get(popular_key))
