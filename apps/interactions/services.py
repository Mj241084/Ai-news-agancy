from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Tuple

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError
from django.db.models import Avg, Count, ExpressionWrapper, F, FloatField, Q, Sum, Value
from django.utils import timezone

from apps.content.models import Article
from apps.interactions.models import ArticleRating, DailyArticleInteraction, Visitor

# NOTE:
# DailyArticleInteraction still contains likes/bookmarks fields for historical compatibility,
# but the application no longer records or uses "like" and "bookmark" as a core interaction signal.

COUNTER_FIELDS = (
    "views",
    "clicks",
    "likes",
    "shares",
    "bookmarks",
    "dwell_seconds",
)

EVENT_TO_FIELD = {
    "view": "views",
    "click": "clicks",
    "share": "shares",
}


def get_or_create_visitor_from_request(request) -> Visitor:
    cookie_name = getattr(settings, "VISITOR_COOKIE_NAME", "anon_id")
    anon_id = request.COOKIES.get(cookie_name)

    if not anon_id:
        anon_id = str(uuid.uuid4())
        request._visitor_set_cookie = True

    user = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
    visitor, _ = Visitor.objects.get_or_create(anon_id=anon_id, defaults={"user": user})

    if user and visitor.user_id != user.id:
        Visitor.objects.filter(pk=visitor.pk).update(user=user)
        visitor.user = user

    request._visitor_anon_id = anon_id
    return visitor


def touch_visitor(visitor: Visitor) -> None:
    interval_seconds = getattr(settings, "VISITOR_TOUCH_INTERVAL_SECONDS", 3600)
    threshold = timezone.now() - timedelta(seconds=interval_seconds)

    if visitor.last_seen <= threshold:
        now = timezone.now()
        Visitor.objects.filter(pk=visitor.pk).update(last_seen=now)
        visitor.last_seen = now


def _resolve_actor(actor) -> Tuple[object, Visitor]:
    user_model = get_user_model()

    if isinstance(actor, Visitor):
        return None, actor

    if isinstance(actor, user_model):
        if not actor.is_authenticated:
            raise ValueError("Anonymous users are not valid actors; pass a Visitor.")
        return actor, None

    if hasattr(actor, "is_authenticated") and actor.is_authenticated:
        return actor, None

    raise TypeError("Actor must be an authenticated user or Visitor instance.")


def _increment_interaction(actor, article: Article, **increments) -> DailyArticleInteraction:
    if not isinstance(article, Article):
        raise TypeError("article must be an Article instance")

    user, visitor = _resolve_actor(actor)
    today = timezone.localdate()

    base_lookup = {
        "date": today,
        "article": article,
        "user": user if user else None,
        "visitor": visitor if visitor else None,
    }

    update_kwargs = {field: F(field) + value for field, value in increments.items() if value}

    if update_kwargs:
        updated = DailyArticleInteraction.objects.filter(**base_lookup).update(**update_kwargs)
        if updated:
            return DailyArticleInteraction.objects.get(**base_lookup)

    defaults = {field: 0 for field in COUNTER_FIELDS}
    for field, value in increments.items():
        defaults[field] = max(int(value), 0)

    try:
        return DailyArticleInteraction.objects.create(**base_lookup, **defaults)
    except IntegrityError:
        if update_kwargs:
            DailyArticleInteraction.objects.filter(**base_lookup).update(**update_kwargs)
        return DailyArticleInteraction.objects.get(**base_lookup)


def log_view(actor, article: Article) -> DailyArticleInteraction:
    return _increment_interaction(actor, article, views=1)


def log_click(actor, article: Article) -> DailyArticleInteraction:
    return _increment_interaction(actor, article, clicks=1)


def log_share(actor, article: Article) -> DailyArticleInteraction:
    return _increment_interaction(actor, article, shares=1)


def add_dwell_seconds(actor, article: Article, seconds: int) -> DailyArticleInteraction | None:
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return _increment_interaction(actor, article, dwell_seconds=seconds)


def log_event(actor, article: Article, event_type: str, seconds: int | None = None):
    event_type = (event_type or "").strip().lower()

    if event_type == "view":
        user, visitor = _resolve_actor(actor)
        actor_key = f"user:{user.id}" if user else f"visitor:{visitor.anon_id}"
        dedupe_key = f"view_dedupe:{actor_key}:{article.id}"
        if not cache.add(dedupe_key, "1", timeout=30 * 60):
            return None

    if event_type == "dwell":
        return add_dwell_seconds(actor, article, seconds or 0)

    counter_field = EVENT_TO_FIELD.get(event_type)
    if not counter_field:
        raise ValueError(f"Unsupported event_type: {event_type}")

    return _increment_interaction(actor, article, **{counter_field: 1})


def set_article_rating(actor, article: Article, *, value: int) -> dict:
    if not isinstance(article, Article):
        raise TypeError("article must be an Article instance")

    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ValueError("Rating must be an integer between 1 and 5.")

    if value < 1 or value > 5:
        raise ValueError("Rating must be between 1 and 5.")

    user, visitor = _resolve_actor(actor)

    existing = ArticleRating.objects.filter(
        article=article,
        user=user if user else None,
        visitor=visitor if visitor else None,
    ).first()

    if existing:
        changed = existing.value != value
        if changed:
            existing.value = value
            existing.save(update_fields=["value", "updated_at"])
        rating = existing
    else:
        rating = ArticleRating.objects.create(
            article=article,
            user=user,
            visitor=visitor,
            value=value,
        )
        changed = True

    return {"value": rating.value, "changed": changed}


def get_article_rating_stats(article_id: int) -> dict:
    payload = ArticleRating.objects.filter(article_id=article_id).aggregate(
        rating_avg=Avg("value"),
        rating_count=Count("id"),
    )
    avg = payload.get("rating_avg")
    count = int(payload.get("rating_count") or 0)
    return {
        "rating_avg": round(float(avg), 2) if avg is not None else 0.0,
        "rating_count": count,
    }


def get_actor_article_rating(actor, article_id: int) -> int | None:
    try:
        user, visitor = _resolve_actor(actor)
    except (TypeError, ValueError):
        return None

    row = ArticleRating.objects.filter(
        article_id=article_id,
        user=user if user else None,
        visitor=visitor if visitor else None,
    ).values("value").first()
    if not row:
        return None
    try:
        return int(row.get("value"))
    except (TypeError, ValueError):
        return None


def _weighted_popularity_expression():
    # Replaced the old "like/bookmark" signal with dwell + rating (applied later).
    return ExpressionWrapper(
        F("views")
        + 2 * F("clicks")
        + 8 * F("shares")
        + (F("dwell_seconds") / Value(30.0)),
        output_field=FloatField(),
    )


def get_article_stats(article_id: int, days: int | None = None) -> dict:
    qs = DailyArticleInteraction.objects.filter(article_id=article_id)

    if days:
        start_date = timezone.localdate() - timedelta(days=max(days - 1, 0))
        qs = qs.filter(date__gte=start_date)

    stats = qs.aggregate(
        views=Sum("views"),
        clicks=Sum("clicks"),
        shares=Sum("shares"),
        dwell_seconds=Sum("dwell_seconds"),
    )

    normalized = {key: int(value or 0) for key, value in stats.items()}
    normalized["score"] = (
        normalized["views"]
        + 2 * normalized["clicks"]
        + 8 * normalized["shares"]
        + (normalized["dwell_seconds"] / 30.0)
    )

    normalized.update(get_article_rating_stats(article_id))
    return normalized


def get_popular_article_scores(
    *,
    days: int | None = None,
    article_ids: list[int] | None = None,
    limit: int | None = None,
) -> dict[int, float]:
    qs = DailyArticleInteraction.objects.all()

    if days is None:
        days = getattr(settings, "POPULAR_LOOKBACK_DAYS", 7)

    if days:
        start_date = timezone.localdate() - timedelta(days=max(days - 1, 0))
        qs = qs.filter(date__gte=start_date)

    if article_ids is not None:
        if not article_ids:
            return {}
        qs = qs.filter(article_id__in=article_ids)

    base_rows = list(
        qs.values("article_id").annotate(base_score=Sum(_weighted_popularity_expression()))
    )

    if not base_rows:
        # Popularity can still be driven by ratings alone.
        if article_ids:
            rating_rows = ArticleRating.objects.filter(article_id__in=article_ids).values("article_id").annotate(
                rating_avg=Avg("value"),
                rating_count=Count("id"),
            )
            scores = {}
            for row in rating_rows:
                avg = float(row.get("rating_avg") or 0)
                cnt = int(row.get("rating_count") or 0)
                scores[row["article_id"]] = avg * cnt * 5.0
            if limit:
                scores = dict(sorted(scores.items(), key=lambda x: x[1], reverse=True)[:limit])
            return scores
        return {}

    ids = [row["article_id"] for row in base_rows]

    rating_rows = ArticleRating.objects.filter(article_id__in=ids).values("article_id").annotate(
        rating_avg=Avg("value"),
        rating_count=Count("id"),
    )
    rating_map = {
        row["article_id"]: (float(row.get("rating_avg") or 0), int(row.get("rating_count") or 0))
        for row in rating_rows
    }

    scores = {}
    for row in base_rows:
        aid = row["article_id"]
        base_score = float(row.get("base_score") or 0)
        avg, cnt = rating_map.get(aid, (0.0, 0))
        rating_boost = avg * cnt * 5.0
        scores[aid] = base_score + rating_boost

    # Apply ordering after combining signals.
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    if limit:
        ordered = ordered[:limit]
    return dict(ordered)
