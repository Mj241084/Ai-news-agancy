from __future__ import annotations

import math
from collections import defaultdict
from datetime import date as date_type, datetime, time, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.content.models import Article, ArticleCategory, ArticleEntity, ArticleTag
from apps.entities.models import Entity
from apps.interactions.models import DailyArticleInteraction, Visitor
from apps.interactions.services import get_popular_article_scores
from apps.relations.models import ArticleRelation
from apps.taxonomy.models import Category, Tag

ROLE_WEIGHTS = {
    ArticleEntity.ROLE_MAIN: 2.0,
    ArticleEntity.ROLE_MENTIONED: 1.0,
    ArticleEntity.ROLE_AUTHOR: 1.2,
    ArticleEntity.ROLE_TARGET: 1.2,
}



def _normalize_date(value: date_type | None) -> date_type:
    return value or timezone.localdate()



def _date_key(value: date_type) -> str:
    return value.strftime("%Y%m%d")



def _current_algo_version(algo_version: str | None = None) -> str:
    return algo_version or getattr(settings, "PERSONALIZATION_ALGO_VERSION", "v1")



def _ttl_until_end_of_day(for_date: date_type) -> int:
    today = timezone.localdate()
    if for_date != today:
        return 86400

    tz = timezone.get_current_timezone()
    now = timezone.localtime(timezone.now(), tz)
    midnight_next = timezone.make_aware(datetime.combine(today + timedelta(days=1), time.min), tz)
    seconds = int((midnight_next - now).total_seconds())
    return max(seconds, 60)



def _actor_cache_prefix(actor) -> str:
    user_model = get_user_model()

    if isinstance(actor, Visitor):
        return f"anon:{actor.anon_id}"

    if isinstance(actor, user_model) or hasattr(actor, "is_authenticated"):
        if not actor.is_authenticated:
            raise ValueError("Anonymous users are not valid personalization actors.")
        return f"user:{actor.id}"

    raise TypeError("Actor must be a Visitor or authenticated user.")



def _is_visitor(actor) -> bool:
    return isinstance(actor, Visitor)



def _interest_cache_key(actor, for_date: date_type, algo_version: str) -> str:
    prefix = _actor_cache_prefix(actor)
    return f"interest:{prefix}:{_date_key(for_date)}:{algo_version}"



def _recs_cache_key(actor, for_date: date_type, algo_version: str) -> str:
    prefix = _actor_cache_prefix(actor)
    return f"recs:{prefix}:{_date_key(for_date)}:{algo_version}"



def _extract_actor_filters(actor) -> tuple[dict, dict]:
    user_model = get_user_model()

    if isinstance(actor, Visitor):
        return {"visitor": actor}, {"type": "visitor", "id": actor.id, "anon_id": actor.anon_id}

    if isinstance(actor, user_model) or hasattr(actor, "is_authenticated"):
        if not actor.is_authenticated:
            raise ValueError("Anonymous users are not valid personalization actors.")
        return {"user": actor}, {"type": "user", "id": actor.id}

    raise TypeError("Actor must be a Visitor or authenticated user")



def _engagement_score(row: dict, for_date: date_type) -> float:
    days_ago = max((for_date - row["date"]).days, 0)
    decay = math.exp(-days_ago / 14.0)

    base_score = (
        float(row.get("views", 0)) * 1.0
        + float(row.get("clicks", 0)) * 2.0
                + float(row.get("shares", 0)) * 8.0
                + min(float(row.get("dwell_seconds", 0)) / 30.0, 3.0)
    )

    return max(base_score * decay, 0.0)



def _normalize_top_scores(score_map: dict[int, float], top_k: int) -> list[tuple[int, float, float]]:
    if not score_map:
        return []

    ranked = sorted(score_map.items(), key=lambda item: item[1], reverse=True)[:top_k]
    max_score = ranked[0][1] if ranked and ranked[0][1] > 0 else 1.0

    return [
        (feature_id, round(raw_score / max_score, 6), round(raw_score, 6))
        for feature_id, raw_score in ranked
    ]



def _build_interest_profile_from_actor(actor, for_date: date_type, *, algo_version: str) -> dict:
    actor_filters, actor_payload = _extract_actor_filters(actor)
    window_days = int(getattr(settings, "INTEREST_WINDOW_DAYS", 30))
    start_date = for_date - timedelta(days=max(window_days - 1, 0))

    interaction_rows = list(
        DailyArticleInteraction.objects.filter(
            **actor_filters,
            date__gte=start_date,
            date__lte=for_date,
            article__status=Article.STATUS_PUBLISHED,
        ).values(
            "article_id",
            "date",
            "views",
            "clicks",
            "shares",
            "dwell_seconds",
        )
    )

    article_engagement: dict[int, float] = defaultdict(float)
    for row in interaction_rows:
        engagement = _engagement_score(row, for_date)
        if engagement <= 0:
            continue
        article_engagement[row["article_id"]] += engagement

    category_scores: dict[int, float] = defaultdict(float)
    entity_scores: dict[int, float] = defaultdict(float)
    tag_scores: dict[int, float] = defaultdict(float)

    article_ids = list(article_engagement.keys())

    if article_ids:
        for row in ArticleCategory.objects.filter(article_id__in=article_ids).values(
            "article_id",
            "category_id",
            "is_primary",
            "weight",
        ):
            engagement = article_engagement.get(row["article_id"], 0.0)
            if engagement <= 0:
                continue
            base_w = float(row.get("weight") or 1.0)
            category_weight = base_w * (1.5 if row["is_primary"] else 1.0)
            category_scores[row["category_id"]] += engagement * category_weight

        for row in ArticleEntity.objects.filter(article_id__in=article_ids).values(
            "article_id",
            "entity_id",
            "role",
            "importance",
        ):
            engagement = article_engagement.get(row["article_id"], 0.0)
            if engagement <= 0:
                continue
            role_weight = ROLE_WEIGHTS.get(row["role"], 1.0)
            importance = max(float(row.get("importance") or 1.0), 0.0)
            entity_scores[row["entity_id"]] += engagement * role_weight * importance

        for row in ArticleTag.objects.filter(article_id__in=article_ids).values("article_id", "tag_id"):
            engagement = article_engagement.get(row["article_id"], 0.0)
            if engagement <= 0:
                continue
            tag_scores[row["tag_id"]] += engagement * 0.6

    if actor_payload["type"] == "user":
        profile = (
            UserProfile.objects.filter(user_id=actor_payload["id"])
            .prefetch_related("preferred_categories", "preferred_entities", "preferred_tags")
            .first()
        )
        if profile:
            category_boost = max(sum(category_scores.values()) * 0.05, 0.1)
            for category in profile.preferred_categories.all():
                category_scores[category.id] += category_boost

            entity_boost = max(sum(entity_scores.values()) * 0.05, 0.1)
            for entity in profile.preferred_entities.all():
                entity_scores[entity.id] += entity_boost

            tag_boost = max(sum(tag_scores.values()) * 0.05, 0.1)
            for tag in profile.preferred_tags.all():
                tag_scores[tag.id] += tag_boost

    top_categories_raw = _normalize_top_scores(
        category_scores,
        int(getattr(settings, "INTEREST_TOP_CATEGORIES", 10)),
    )
    top_entities_raw = _normalize_top_scores(
        entity_scores,
        int(getattr(settings, "INTEREST_TOP_ENTITIES", 15)),
    )
    top_tags_raw = _normalize_top_scores(
        tag_scores,
        int(getattr(settings, "INTEREST_TOP_TAGS", 15)),
    )

    category_meta = {
        row["id"]: row["slug"]
        for row in Category.objects.filter(id__in=[item[0] for item in top_categories_raw]).values("id", "slug")
    }
    entity_meta = {
        row["id"]: {"slug": row["slug"], "type": row["type"]}
        for row in Entity.objects.filter(id__in=[item[0] for item in top_entities_raw]).values("id", "slug", "type")
    }
    tag_meta = {
        row["id"]: row["slug"]
        for row in Tag.objects.filter(id__in=[item[0] for item in top_tags_raw]).values("id", "slug")
    }

    top_categories = [
        {
            "id": category_id,
            "slug": category_meta.get(category_id, ""),
            "score": score,
            "raw_score": raw_score,
        }
        for category_id, score, raw_score in top_categories_raw
    ]

    top_entities = [
        {
            "id": entity_id,
            "slug": entity_meta.get(entity_id, {}).get("slug", ""),
            "type": entity_meta.get(entity_id, {}).get("type", "other"),
            "score": score,
            "raw_score": raw_score,
        }
        for entity_id, score, raw_score in top_entities_raw
    ]

    top_tags = [
        {
            "id": tag_id,
            "slug": tag_meta.get(tag_id, ""),
            "score": score,
            "raw_score": raw_score,
        }
        for tag_id, score, raw_score in top_tags_raw
    ]

    top_seed_size = int(getattr(settings, "INTEREST_TOP_SEEDS", 20))
    seed_rank = sorted(article_engagement.items(), key=lambda item: item[1], reverse=True)[:top_seed_size]

    seed_meta = {
        row["id"]: row["slug"]
        for row in Article.objects.filter(id__in=[item[0] for item in seed_rank]).values("id", "slug")
    }
    seed_max = seed_rank[0][1] if seed_rank and seed_rank[0][1] > 0 else 1.0

    seed_articles = [
        {
            "id": article_id,
            "slug": seed_meta.get(article_id, ""),
            "score": round(raw_score, 6),
            "norm_score": round(raw_score / seed_max, 6),
        }
        for article_id, raw_score in seed_rank
    ]

    return {
        "algo_version": algo_version,
        "date": for_date.isoformat(),
        "window_days": window_days,
        "actor": actor_payload,
        "top_categories": top_categories,
        "top_entities": top_entities,
        "top_tags": top_tags,
        "seed_articles": seed_articles,
    }



def compute_daily_interest_for_user(user, date: date_type, algo_version: str | None = None) -> dict:
    if not user or not user.is_authenticated:
        raise ValueError("User must be authenticated")

    for_date = _normalize_date(date)
    algo_version = _current_algo_version(algo_version)
    return _build_interest_profile_from_actor(user, for_date, algo_version=algo_version)



def compute_daily_interest_for_visitor(visitor: Visitor, date: date_type, algo_version: str | None = None) -> dict:
    if not isinstance(visitor, Visitor):
        raise TypeError("visitor must be a Visitor instance")

    for_date = _normalize_date(date)
    algo_version = _current_algo_version(algo_version)
    return _build_interest_profile_from_actor(visitor, for_date, algo_version=algo_version)



def _recent_seen_article_ids(actor, for_date: date_type, days: int) -> set[int]:
    actor_filters, _ = _extract_actor_filters(actor)
    start_date = for_date - timedelta(days=max(days - 1, 0))

    return set(
        DailyArticleInteraction.objects.filter(
            **actor_filters,
            date__gte=start_date,
            date__lte=for_date,
        ).values_list("article_id", flat=True)
    )



def _max_normalized_map(values: dict[int, float]) -> dict[int, float]:
    if not values:
        return {}
    max_value = max(values.values())
    if max_value <= 0:
        return {key: 0.0 for key in values}
    return {key: float(value / max_value) for key, value in values.items()}



def compute_daily_recommendations(
    interest_profile: dict,
    date: date_type,
    actor=None,
    algo_version: str | None = None,
) -> list[dict]:
    for_date = _normalize_date(date)
    algo_version = _current_algo_version(algo_version)

    top_n = int(getattr(settings, "RECS_TOP_N", 30))
    max_candidates = int(getattr(settings, "RECS_MAX_CANDIDATES", 1000))
    recent_days = int(getattr(settings, "RECS_RECENT_DAYS", 14))
    exclude_days = int(getattr(settings, "RECS_EXCLUDE_SEEN_DAYS", 14))
    seed_relation_limit = int(getattr(settings, "RECS_SEED_RELATION_LIMIT", 20))

    category_pref = {item["id"]: float(item.get("score", 0.0)) for item in interest_profile.get("top_categories", []) if item.get("id")}
    entity_pref = {item["id"]: float(item.get("score", 0.0)) for item in interest_profile.get("top_entities", []) if item.get("id")}
    tag_pref = {item["id"]: float(item.get("score", 0.0)) for item in interest_profile.get("top_tags", []) if item.get("id")}

    seed_articles = [item for item in interest_profile.get("seed_articles", []) if item.get("id")]
    seed_max = max([float(item.get("score", 0.0)) for item in seed_articles], default=1.0)
    seed_slug_map = {int(item["id"]): item.get("slug", "") for item in seed_articles}

    now = timezone.now()
    recent_cutoff = now - timedelta(days=max(recent_days, 1))

    published_qs = Article.objects.filter(
        status=Article.STATUS_PUBLISHED,
        published_at__isnull=False,
    )

    candidate_ids: set[int] = set()

    if category_pref:
        category_ids = list(category_pref.keys())[:8]
        candidate_ids.update(
            published_qs.filter(article_categories__category_id__in=category_ids, published_at__gte=recent_cutoff)
            .order_by("-published_at")
            .values_list("id", flat=True)
            .distinct()[:400]
        )

    if entity_pref:
        entity_ids = list(entity_pref.keys())[:12]
        candidate_ids.update(
            published_qs.filter(article_entities__entity_id__in=entity_ids, published_at__gte=recent_cutoff)
            .order_by("-published_at")
            .values_list("id", flat=True)
            .distinct()[:400]
        )

    if tag_pref:
        tag_ids = list(tag_pref.keys())[:12]
        candidate_ids.update(
            published_qs.filter(article_tags__tag_id__in=tag_ids, published_at__gte=recent_cutoff)
            .order_by("-published_at")
            .values_list("id", flat=True)
            .distinct()[:300]
        )

    graph_scores: dict[int, float] = defaultdict(float)
    graph_reasons: dict[int, str] = {}
    graph_reason_best: dict[int, float] = defaultdict(float)

    for seed in seed_articles[:10]:
        seed_id = int(seed["id"])
        seed_weight = float(seed.get("score") or 0.0) / (seed_max or 1.0)

        relation_rows = list(
            ArticleRelation.objects.filter(algo_version=algo_version)
            .filter(Q(article_a_id=seed_id) | Q(article_b_id=seed_id))
            .order_by("-score")
            .values("article_a_id", "article_b_id", "score")[:seed_relation_limit]
        )

        for row in relation_rows:
            other_id = row["article_b_id"] if row["article_a_id"] == seed_id else row["article_a_id"]
            contribution = float(row["score"] or 0.0) * seed_weight
            if contribution <= 0:
                continue

            candidate_ids.add(other_id)
            graph_scores[other_id] += contribution
            if contribution >= graph_reason_best.get(other_id, 0.0):
                graph_reasons[other_id] = seed_slug_map.get(seed_id, "")
                graph_reason_best[other_id] = contribution

    team_pick_ids = list(
        published_qs.filter(is_team_pick=True, published_at__gte=now - timedelta(days=45))
        .order_by("-published_at")
        .values_list("id", flat=True)[:250]
    )
    candidate_ids.update(team_pick_ids)

    popular_map = get_popular_article_scores(days=getattr(settings, "POPULAR_LOOKBACK_DAYS", 7), limit=400)
    candidate_ids.update(popular_map.keys())

    latest_ids = list(published_qs.order_by("-published_at").values_list("id", flat=True)[:400])
    candidate_ids.update(latest_ids)

    if actor is not None:
        seen_ids = _recent_seen_article_ids(actor, for_date, exclude_days)
        candidate_ids.difference_update(seen_ids)

    if not candidate_ids:
        return []

    candidate_articles = list(
        Article.objects.filter(id__in=candidate_ids, status=Article.STATUS_PUBLISHED)
        .only("id", "slug", "title", "content_type", "published_at", "is_team_pick")
    )

    if not candidate_articles:
        return []

    popular_norm_map = _max_normalized_map({article_id: float(score) for article_id, score in popular_map.items()})

    def heuristic_score(article: Article) -> float:
        days_ago = max((for_date - article.published_at.date()).days, 0) if article.published_at else 365
        freshness = math.exp(-days_ago / 14.0)
        return (
            graph_scores.get(article.id, 0.0) * 2.0
            + popular_norm_map.get(article.id, 0.0) * 0.8
            + (0.4 if article.is_team_pick else 0.0)
            + freshness
        )

    candidate_articles.sort(key=heuristic_score, reverse=True)
    candidate_articles = candidate_articles[:max_candidates]

    selected_ids = [article.id for article in candidate_articles]

    category_links: dict[int, list[tuple[int, bool, float]]] = defaultdict(list)
    for row in ArticleCategory.objects.filter(article_id__in=selected_ids).values("article_id", "category_id", "is_primary", "weight"):
        category_links[row["article_id"]].append((row["category_id"], bool(row["is_primary"]), float(row.get("weight") or 1.0)))

    entity_links: dict[int, list[tuple[int, str, float]]] = defaultdict(list)
    for row in ArticleEntity.objects.filter(article_id__in=selected_ids).values(
        "article_id",
        "entity_id",
        "role",
        "importance",
    ):
        entity_links[row["article_id"]].append(
            (
                row["entity_id"],
                row["role"],
                float(row.get("importance") or 1.0),
            )
        )

    tag_links: dict[int, set[int]] = defaultdict(set)
    for row in ArticleTag.objects.filter(article_id__in=selected_ids).values("article_id", "tag_id"):
        tag_links[row["article_id"]].add(row["tag_id"])

    category_slug_map = {
        item["id"]: item.get("slug", "")
        for item in interest_profile.get("top_categories", [])
        if item.get("id")
    }
    entity_slug_map = {
        item["id"]: item.get("slug", "")
        for item in interest_profile.get("top_entities", [])
        if item.get("id")
    }
    tag_slug_map = {
        item["id"]: item.get("slug", "")
        for item in interest_profile.get("top_tags", [])
        if item.get("id")
    }

    raw_cat: dict[int, float] = {}
    raw_ent: dict[int, float] = {}
    raw_tag: dict[int, float] = {}
    raw_graph: dict[int, float] = {}
    raw_fresh: dict[int, float] = {}
    raw_team: dict[int, float] = {}
    raw_pop: dict[int, float] = {}

    for article in candidate_articles:
        days_ago = max((for_date - article.published_at.date()).days, 0) if article.published_at else 365

        cat_score = 0.0
        for category_id, is_primary, weight in category_links.get(article.id, []):
            pref_score = category_pref.get(category_id, 0.0)
            if pref_score <= 0:
                continue
            cat_score += pref_score * (float(weight or 1.0) * (1.5 if is_primary else 1.0))

        ent_score = 0.0
        for entity_id, role, importance in entity_links.get(article.id, []):
            pref_score = entity_pref.get(entity_id, 0.0)
            if pref_score <= 0:
                continue
            ent_score += pref_score * ROLE_WEIGHTS.get(role, 1.0) * max(importance, 0.0)

        tag_score = 0.0
        for tag_id in tag_links.get(article.id, set()):
            tag_score += tag_pref.get(tag_id, 0.0)

        raw_cat[article.id] = cat_score
        raw_ent[article.id] = ent_score
        raw_tag[article.id] = tag_score
        raw_graph[article.id] = graph_scores.get(article.id, 0.0)
        raw_fresh[article.id] = math.exp(-days_ago / 14.0)
        raw_team[article.id] = 1.0 if article.is_team_pick else 0.0
        raw_pop[article.id] = popular_norm_map.get(article.id, 0.0)

    norm_cat = _max_normalized_map(raw_cat)
    norm_ent = _max_normalized_map(raw_ent)
    norm_tag = _max_normalized_map(raw_tag)
    norm_graph = _max_normalized_map(raw_graph)

    recommendations = []

    for article in candidate_articles:
        article_id = article.id

        component_scores = {
            "entity": 0.35 * norm_ent.get(article_id, 0.0),
            "category": 0.25 * norm_cat.get(article_id, 0.0),
            "related": 0.20 * norm_graph.get(article_id, 0.0),
            "fresh": 0.15 * raw_fresh.get(article_id, 0.0),
            "team_pick": 0.05 * raw_team.get(article_id, 0.0),
            "popular": 0.03 * raw_pop.get(article_id, 0.0),
            "tag": 0.02 * norm_tag.get(article_id, 0.0),
        }

        final_score = min(sum(component_scores.values()), 1.0)
        if final_score <= 0:
            continue

        reason_key = max(component_scores, key=component_scores.get)
        reason = {"type": reason_key}

        if reason_key == "related":
            reason["from"] = graph_reasons.get(article_id, "")
        elif reason_key == "entity":
            matches = [
                (
                    entity_id,
                    entity_pref.get(entity_id, 0.0) * ROLE_WEIGHTS.get(role, 1.0) * max(importance, 0.0),
                )
                for entity_id, role, importance in entity_links.get(article_id, [])
                if entity_id in entity_pref
            ]
            if matches:
                entity_id = max(matches, key=lambda item: item[1])[0]
                reason["value"] = entity_slug_map.get(entity_id, "")
        elif reason_key == "category":
            matches = [
                (
                    category_id,
                    category_pref.get(category_id, 0.0) * (1.5 if is_primary else 1.0),
                )
                for category_id, is_primary in category_links.get(article_id, [])
                if category_id in category_pref
            ]
            if matches:
                category_id = max(matches, key=lambda item: item[1])[0]
                reason["value"] = category_slug_map.get(category_id, "")
        elif reason_key == "tag":
            matches = [(tag_id, tag_pref.get(tag_id, 0.0)) for tag_id in tag_links.get(article_id, set()) if tag_id in tag_pref]
            if matches:
                tag_id = max(matches, key=lambda item: item[1])[0]
                reason["value"] = tag_slug_map.get(tag_id, "")

        recommendations.append(
            {
                "id": article.id,
                "slug": article.slug,
                "title": article.title,
                "url": article.get_absolute_url(),
                "published_at": article.published_at.isoformat() if article.published_at else None,
                "content_type": article.content_type,
                "is_team_pick": article.is_team_pick,
                "score": round(final_score, 6),
                "reason": reason,
            }
        )

    recommendations.sort(
        key=lambda item: (
            item["score"],
            item["published_at"] or "",
            item["id"],
        ),
        reverse=True,
    )

    return recommendations[:top_n]



def ensure_daily_interest_cached(
    actor,
    date: date_type | None = None,
    algo_version: str | None = None,
) -> dict:
    for_date = _normalize_date(date)
    resolved_algo_version = _current_algo_version(algo_version)
    cache_key = _interest_cache_key(actor, for_date, resolved_algo_version)

    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    if _is_visitor(actor):
        computed = compute_daily_interest_for_visitor(actor, for_date, algo_version=resolved_algo_version)
    else:
        computed = compute_daily_interest_for_user(actor, for_date, algo_version=resolved_algo_version)

    cache.set(cache_key, computed, timeout=_ttl_until_end_of_day(for_date))
    return computed



def ensure_daily_recs_cached(
    actor,
    date: date_type | None = None,
    algo_version: str | None = None,
) -> list[dict]:
    for_date = _normalize_date(date)
    resolved_algo_version = _current_algo_version(algo_version)
    cache_key = _recs_cache_key(actor, for_date, resolved_algo_version)

    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    interest_profile = ensure_daily_interest_cached(actor, date=for_date, algo_version=resolved_algo_version)
    recommendations = compute_daily_recommendations(
        interest_profile,
        for_date,
        actor=actor,
        algo_version=resolved_algo_version,
    )
    cache.set(cache_key, recommendations, timeout=_ttl_until_end_of_day(for_date))
    return recommendations
