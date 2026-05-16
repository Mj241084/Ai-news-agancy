from __future__ import annotations

from django.core.cache import cache
from django.http import QueryDict
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.content.cache_invalidation import invalidate_article_cache
from apps.content.models import Article, ArticleCategory
from apps.core.sitemap_cache import SITEMAP_XML_CACHE_KEY
from apps.seo.context import clean_querydict_for_canonical
from apps.taxonomy.models import Category, Tag


@override_settings(SITE_BASE_URL="https://news.test")
class SeoPhase6Tests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            title="هوش مصنوعی",
            slug="ai",
            is_active=True,
            is_indexable=True,
        )
        self.article = Article.objects.create(
            content_type=Article.CONTENT_SHORT_NEWS,
            status=Article.STATUS_PUBLISHED,
            title="خبر تست",
            slug="test-news",
            excerpt="خلاصه خبر تست",
            body="**متن** خبر تست برای بررسی JSON-LD",
            language="fa",
        )
        ArticleCategory.objects.create(
            article=self.article,
            category=self.category,
            is_primary=True,
            weight=1.0,
        )

        self.post = Article.objects.create(
            content_type=Article.CONTENT_POST,
            status=Article.STATUS_PUBLISHED,
            title="پست تست",
            slug="test-post",
            excerpt="خلاصه پست تست",
            body="متن پست تست",
            language="fa",
        )
        ArticleCategory.objects.create(
            article=self.post,
            category=self.category,
            is_primary=True,
            weight=1.0,
        )

    def test_search_page_is_noindex(self):
        response = self.client.get(reverse("core:search"), {"q": "ai"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<meta name="robots" content="noindex,follow">', html=True)

    def test_article_canonical_is_absolute_and_query_clean(self):
        url = f"{reverse('content:detail', args=[self.article.slug])}?utm_source=test&ref=abc"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'rel="canonical" href="https://news.test/p/test-news/"',
            html=False,
        )
        self.assertNotContains(response, "utm_source=test")
        self.assertNotContains(response, "ref=abc")

    def test_article_jsonld_exists(self):
        response = self.client.get(reverse("content:detail", args=[self.article.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'type="application/ld+json"', html=False)
        self.assertContains(response, '"@type":"NewsArticle"', html=False)
        self.assertContains(response, '"@type":"BreadcrumbList"', html=False)

    def test_article_meta_robots_override(self):
        self.article.meta_robots = " NOINDEX , FOLLOW "
        self.article.save(update_fields=["meta_robots"])

        response = self.client.get(reverse("content:detail", args=[self.article.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<meta name="robots" content="noindex,follow">', html=False)


    def test_post_detail_is_noindex_follow(self):
        response = self.client.get(reverse("content:detail", args=[self.post.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<meta name="robots" content="noindex,follow">', html=False)

    def test_post_not_in_sitemap(self):
        response = self.client.get("/sitemap.xml")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "/p/test-post/", html=False)

    def test_category_and_tag_is_indexable_false_force_noindex(self):
        self.category.is_indexable = False
        self.category.save(update_fields=["is_indexable"])

        tag = Tag.objects.create(
            title="تست",
            slug="test-tag",
            is_active=True,
            is_indexable=False,
        )

        category_response = self.client.get(reverse("taxonomy:category_detail", kwargs={"category_slug": self.category.slug}))
        self.assertEqual(category_response.status_code, 200)
        self.assertContains(category_response, '<meta name="robots" content="noindex,follow">', html=True)

        tag_response = self.client.get(reverse("taxonomy:tag_detail", kwargs={"tag_slug": tag.slug}))
        self.assertEqual(tag_response.status_code, 200)
        self.assertContains(tag_response, '<meta name="robots" content="noindex,follow">', html=True)

    def test_category_canonical_drops_page_1_and_default_filters(self):
        response = self.client.get(
            reverse("taxonomy:category_detail", kwargs={"category_slug": self.category.slug}),
            {
                "page": 1,
                "sort": "latest",
                "type": "all",
                "sub": 1,
                "utm_source": "ads",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'rel="canonical" href="https://news.test{reverse("taxonomy:category_detail", kwargs={"category_slug": self.category.slug})}"',
            html=False,
        )
        self.assertNotContains(response, "page=1")
        self.assertNotContains(response, "sort=latest")
        self.assertNotContains(response, "type=all")
        self.assertNotContains(response, "sub=1")
        self.assertNotContains(response, "utm_source")

    def test_sitemap_xml_available(self):
        response = self.client.get("/sitemap.xml")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<urlset", html=False)
        self.assertContains(response, "/p/test-news/", html=False)

    def test_sitemap_cache_invalidation_after_article_change(self):
        first_response = self.client.get("/sitemap.xml")
        self.assertEqual(first_response.status_code, 200)
        self.assertIsNotNone(cache.get(SITEMAP_XML_CACHE_KEY))

        new_article = Article.objects.create(
            content_type=Article.CONTENT_SHORT_NEWS,
            status=Article.STATUS_PUBLISHED,
            title="خبر جدید",
            slug="new-news",
            excerpt="خلاصه خبر جدید",
            body="متن خبر جدید",
            language="fa",
        )
        ArticleCategory.objects.create(
            article=new_article,
            category=self.category,
            is_primary=True,
            weight=1.0,
        )

        invalidate_article_cache(new_article)
        self.assertIsNone(cache.get(SITEMAP_XML_CACHE_KEY))

        second_response = self.client.get("/sitemap.xml")
        self.assertEqual(second_response.status_code, 200)
        self.assertContains(second_response, "/p/new-news/", html=False)

    def test_robots_txt_available(self):
        response = self.client.get("/robots.txt")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Disallow: /staff/", html=False)
        self.assertContains(response, "Disallow: /api/", html=False)
        self.assertContains(response, "Sitemap: https://news.test/sitemap.xml", html=False)

    def test_clean_querydict_allowlist_none_differs_from_empty_set(self):
        querydict = QueryDict("page=2&sort=latest&utm_source=google&ref=home")
        passthrough = clean_querydict_for_canonical(querydict, allowlist=None)
        self.assertEqual(passthrough, "page=2&sort=latest")

        blocked = clean_querydict_for_canonical(querydict, allowlist=set())
        self.assertEqual(blocked, "")

    def test_json_endpoints_have_x_robots_tag(self):
        stats_response = self.client.get(reverse("content:ajax_stats", args=[self.article.slug]))
        self.assertEqual(stats_response.status_code, 200)
        self.assertEqual(stats_response.headers.get("X-Robots-Tag"), "noindex, nofollow")

        search_response = self.client.get(reverse("search:search_api"), {"q": "ai"})
        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(search_response.headers.get("X-Robots-Tag"), "noindex, nofollow")
