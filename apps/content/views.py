from __future__ import annotations

import json

from django.conf import settings
from django.core.paginator import Paginator
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.content.cache_invalidation import invalidate_comment_caches, invalidate_interaction_caches
from apps.content.cache_keys import (
    content_ajax_comments_key,
    content_ajax_related_key,
    content_ajax_stats_key,
    content_article_list_key,
    content_news_list_key,
)
from apps.content import services as content_services
from apps.content.moderation import contains_blocked_comment_word
from apps.content.models import Article, ArticleComment
from apps.content.utils import render_markdown_safe
from apps.interactions.services import (
    get_article_stats,
    get_article_rating_stats,
    get_actor_article_rating,
    get_or_create_visitor_from_request,
    log_event,
    set_article_rating,
)
from apps.relations.services import get_related_articles
from apps.seo.context import build_seo_context
from utils.caching import get_or_set_cached


PAGE_SIZE = 15
COMMENTS_PAGE_SIZE = 20
COMMENT_MAX_LENGTH = 2000


def _safe_int(raw_value, default=1):
    try:
        return max(int(raw_value), 1)
    except (TypeError, ValueError):
        return default


def _json_response(payload: dict, *, status: int = 200):
    response = JsonResponse(payload, status=status)
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


def _parse_json_body(request) -> dict:
    if request.content_type and "application/json" in request.content_type:
        try:
            return json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return {}
    return request.POST.dict()


def _pagination_with_urls(request, payload: dict) -> dict:
    pagination = {
        "page": payload.get("page", 1),
        "page_size": payload.get("page_size", PAGE_SIZE),
        "total": payload.get("total", 0),
        "pages": payload.get("pages", 1),
        "has_next": payload.get("has_next", False),
        "has_previous": payload.get("has_previous", False),
        "next_url": None,
        "prev_url": None,
    }

    if pagination["has_previous"]:
        params = request.GET.copy()
        params["page"] = pagination["page"] - 1
        pagination["prev_url"] = f"?{params.urlencode()}"

    if pagination["has_next"]:
        params = request.GET.copy()
        params["page"] = pagination["page"] + 1
        pagination["next_url"] = f"?{params.urlencode()}"

    return pagination


def _article_from_slug(slug: str) -> Article:
    return get_object_or_404(
        Article,
        slug=slug,
        status=Article.STATUS_PUBLISHED,
        published_at__isnull=False,
    )


def _display_name_for_user(user) -> str:
    full_name = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip()
    return full_name or user.username


def _serialize_comment(comment: ArticleComment) -> dict:
    created_at = timezone.localtime(comment.created_at)
    return {
        "id": comment.id,
        "parent_id": comment.parent_id,
        "author": _display_name_for_user(comment.user),
        "text": comment.text,
        "date": created_at.strftime("%Y/%m/%d %H:%M"),
        "replies": [_serialize_comment(reply) for reply in getattr(comment, "replies", []).all()],
    }



def _build_comments_payload(article: Article, *, page: int) -> dict:
    from django.db.models import Prefetch

    total_visible = ArticleComment.objects.filter(article=article, is_visible=True).count()

    top_level_qs = (
        ArticleComment.objects.filter(article=article, is_visible=True, parent__isnull=True)
        .select_related("user")
        .prefetch_related(
            Prefetch(
                "replies",
                queryset=ArticleComment.objects.filter(article=article, is_visible=True)
                .select_related("user")
                .order_by("created_at", "id"),
            )
        )
        .order_by("-created_at", "-id")
    )

    paginator = Paginator(top_level_qs, COMMENTS_PAGE_SIZE)
    page_obj = paginator.get_page(page)

    return {
        "comments": [_serialize_comment(comment) for comment in page_obj.object_list],
        "total": total_visible,
        "top_level_total": paginator.count,
        "page": page_obj.number,
        "pages": paginator.num_pages or 1,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
    }



@ensure_csrf_cookie
@require_GET
def detail_view(request, slug: str):
    article_data = content_services.get_article_main_cached(slug)
    if article_data is None:
        raise Http404("Article not found")
    if "body_html" not in article_data:
        article_data["body_html"] = render_markdown_safe(article_data.get("body", ""))

    seo = build_seo_context(
        request,
        page_type="article_detail",
        obj=article_data,
        extras={"viewport": "width=device-width, initial-scale=1"},
    )

    context = {
        "article": article_data,
        "active_nav": "news" if article_data.get("content_type") == Article.CONTENT_SHORT_NEWS else "articles",
        "seo": seo,
        "ajax_urls": {
            "stats": reverse("content:ajax_stats", args=[slug]),
            "comments": reverse("content:ajax_comments", args=[slug]),
            "related": reverse("content:ajax_related", args=[slug]),
            "actions": reverse("content:ajax_actions", args=[slug]),
        },
    }
    return render(request, "pages/article_detail.html", context)


@require_GET
def news_list_view(request):
    page = _safe_int(request.GET.get("page", 1), default=1)
    sort_filter = (request.GET.get("sort") or "latest").strip().lower()
    if sort_filter not in {"latest", "popular", "team"}:
        sort_filter = "latest"

    cache_key = content_news_list_key(page=page, sort=sort_filter)

    def _build_payload():
        queryset = content_services.get_published_queryset().filter(content_type=Article.CONTENT_SHORT_NEWS)
        if sort_filter == "popular":
            main = content_services.list_popular(queryset=queryset, page=page, page_size=PAGE_SIZE)
        elif sort_filter == "team":
            main = content_services.list_team_picks(queryset=queryset, page=page, page_size=PAGE_SIZE)
        else:
            main = content_services.list_latest(queryset=queryset, page=page, page_size=PAGE_SIZE)
        popular = content_services.list_popular(queryset=queryset, page=1, page_size=10)
        return {
            "main": main,
            "popular": popular,
        }

    payload = get_or_set_cached(cache_key, settings.PAGE_CACHE_SECONDS, _build_payload)

    robots = "noindex,follow" if sort_filter in {"popular", "team"} else "index,follow"

    context = {
        "items": payload["main"]["items"],
        "popular_items": payload["popular"]["items"],
        "pagination": _pagination_with_urls(request, payload["main"]),
        "filters": {"content_type": "news", "sort": sort_filter},
        "active_nav": "news",
        "seo": build_seo_context(
            request,
            page_type="news_list",
            extras={"sort": sort_filter, "robots": robots},
        ),
    }
    return render(request, "pages/list_news.html", context)


@require_GET
def article_list_view(request):
    page = _safe_int(request.GET.get("page", 1), default=1)
    sort_filter = (request.GET.get("sort") or "latest").strip().lower()
    if sort_filter not in {"latest", "popular", "team"}:
        sort_filter = "latest"

    cache_key = content_article_list_key(page=page, sort=sort_filter)

    def _build_payload():
        queryset = content_services.get_published_queryset().filter(
            content_type__in=[Article.CONTENT_POST, Article.CONTENT_ARTICLE]
        )
        if sort_filter == "popular":
            main = content_services.list_popular(queryset=queryset, page=page, page_size=PAGE_SIZE)
        elif sort_filter == "team":
            main = content_services.list_team_picks(queryset=queryset, page=page, page_size=PAGE_SIZE)
        else:
            main = content_services.list_latest(queryset=queryset, page=page, page_size=PAGE_SIZE)
        team = content_services.list_team_picks(queryset=queryset, page=1, page_size=10)
        return {
            "main": main,
            "team": team,
        }

    payload = get_or_set_cached(cache_key, settings.PAGE_CACHE_SECONDS, _build_payload)

    robots = "noindex,follow" if sort_filter in {"popular", "team"} else "index,follow"

    context = {
        "items": payload["main"]["items"],
        "team_pick_items": payload["team"]["items"],
        "pagination": _pagination_with_urls(request, payload["main"]),
        "filters": {"content_type": "articles", "sort": sort_filter},
        "active_nav": "articles",
        "seo": build_seo_context(
            request,
            page_type="article_list",
            extras={"sort": sort_filter, "robots": robots},
        ),
    }
    return render(request, "pages/list_articles.html", context)


@require_GET
def ajax_stats_view(request, slug: str):
    article = _article_from_slug(slug)
    days = request.GET.get("days")
    days_value = _safe_int(days, default=settings.POPULAR_LOOKBACK_DAYS) if days else None

    cache_key = content_ajax_stats_key(slug=slug, days=days_value or "all")

    def _build_payload():
        stats = get_article_stats(article.id, days=days_value)
        comments_total = ArticleComment.objects.filter(article=article, is_visible=True).count()
        return {
            "views": stats.get("views", 0),
            "clicks": stats.get("clicks", 0),
            "shares": stats.get("shares", 0),
            "dwell_seconds": stats.get("dwell_seconds", 0),
            "rating_avg": stats.get("rating_avg", 0.0),
            "rating_count": stats.get("rating_count", 0),
            "comments": comments_total,
        }

    payload = dict(get_or_set_cached(cache_key, settings.AJAX_CACHE_SECONDS, _build_payload))

    actor = request.user if request.user.is_authenticated else getattr(request, "visitor", None)
    if actor is None:
        actor = get_or_create_visitor_from_request(request)

    payload["user_rating"] = get_actor_article_rating(actor, article.id) or 0
    return _json_response(payload)



@require_http_methods(["GET", "POST"])
def ajax_comments_view(request, slug: str):
    article = _article_from_slug(slug)

    if request.method == "POST":
        if not request.user.is_authenticated:
            return _json_response(
                {
                    "ok": False,
                    "error": "برای ثبت نظر ابتدا وارد حساب شوید.",
                    "login_url": f"{reverse('accounts:login')}?next={article.get_absolute_url()}#comments-section",
                },
                status=401,
            )

        payload = _parse_json_body(request)
        text = (payload.get("text") or "").strip()
        parent_id = payload.get("parent_id")

        if not text:
            return _json_response({"ok": False, "error": "متن نظر نمی‌تواند خالی باشد."}, status=400)
        if len(text) > COMMENT_MAX_LENGTH:
            return _json_response(
                {"ok": False, "error": f"حداکثر {COMMENT_MAX_LENGTH} کاراکتر مجاز است."},
                status=400,
            )
        if contains_blocked_comment_word(text):
            return _json_response(
                {"ok": False, "error": "لطفا از استفاده از کلمات نامناسب خودداری کنید."},
                status=400,
            )

        parent = None
        if parent_id:
            try:
                parent_id_int = int(parent_id)
            except (TypeError, ValueError):
                return _json_response({"ok": False, "error": "شناسه پاسخ نامعتبر است."}, status=400)

            parent = ArticleComment.objects.filter(
                id=parent_id_int,
                article=article,
                is_visible=True,
            ).first()
            if not parent:
                return _json_response({"ok": False, "error": "نظر مادر یافت نشد."}, status=404)

        comment = ArticleComment.objects.create(
            article=article,
            user=request.user,
            parent=parent,
            text=text,
        )
        invalidate_comment_caches(article)
        return _json_response({"ok": True, "comment": _serialize_comment(comment)})

    page = _safe_int(request.GET.get("page", 1), default=1)

    cache_key = content_ajax_comments_key(slug=slug, page=page)

    payload = get_or_set_cached(
        cache_key,
        settings.AJAX_CACHE_SECONDS,
        lambda: _build_comments_payload(article, page=page),
    )
    return _json_response(payload)



@require_GET
def ajax_related_view(request, slug: str):
    article = _article_from_slug(slug)
    limit = _safe_int(request.GET.get("limit", 10), default=10)

    cache_key = content_ajax_related_key(slug=slug, limit=limit)

    def _build_payload():
        items = get_related_articles(article, limit=limit)
        articles = []
        for item in items:
            articles.append(
                {
                    "id": item.get("id"),
                    "slug": item.get("slug"),
                    "title": item.get("title"),
                    "url": item.get("url") or reverse("content:detail", args=[item.get("slug")]),
                    "published_at": item.get("published_at"),
                    "hero_image": item.get("hero_image"),
                    "thumbnail": item.get("thumbnail"),
                }
            )

        return {
            "articles": articles,
            "total": len(articles),
        }

    payload = get_or_set_cached(cache_key, settings.AJAX_CACHE_SECONDS, _build_payload)
    return _json_response(payload)


@require_POST
def ajax_actions_view(request, slug: str):
    article = _article_from_slug(slug)
    payload = _parse_json_body(request)

    event_type = (payload.get("event") or "").strip().lower()
    seconds = payload.get("seconds")
    rating_value = payload.get("value")

    if event_type not in {"view", "click", "share", "dwell", "rating"}:
        return _json_response({"ok": False, "error": "Invalid event type."}, status=400)

    actor = request.user if request.user.is_authenticated else getattr(request, "visitor", None)
    if actor is None:
        actor = get_or_create_visitor_from_request(request)

    if event_type == "rating":
        try:
            rating_payload = set_article_rating(actor, article, value=rating_value)
        except ValueError as exc:
            return _json_response({"ok": False, "error": str(exc)}, status=400)

        invalidate_interaction_caches(article, event_type="rating")
        stats = get_article_rating_stats(article.id)
        return _json_response(
            {
                "ok": True,
                "event": "rating",
                "article_id": article.id,
                "value": rating_payload.get("value"),
                "changed": rating_payload.get("changed", False),
                **stats,
            }
        )

    try:
        log_event(actor, article, event_type, seconds=seconds)
    except ValueError as exc:
        return _json_response({"ok": False, "error": str(exc)}, status=400)

    invalidate_interaction_caches(article, event_type=event_type)
    return _json_response({"ok": True, "event": event_type, "article_id": article.id})
