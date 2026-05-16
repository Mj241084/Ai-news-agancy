from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone as dt_timezone

from django.conf import settings
from django.db import IntegrityError
from django.db.models import Count, Q
from django.utils import timezone

from apps.content.models import Article, ArticleCategory, ArticleEntity, ArticleTag
from apps.relations.models import ArticleRelation
from apps.relations.utils import normalize_article_pair

PERSIAN_STOPWORDS = {
    "و",
    "در",
    "از",
    "به",
    "با",
    "که",
    "را",
    "برای",
    "این",
    "آن",
    "یک",
    "روی",
    "بر",
    "تا",
    "هم",
    "یا",
}

ENGLISH_STOPWORDS = {
    "the",
    "a",
    "an",
    "to",
    "and",
    "of",
    "for",
    "in",
    "on",
    "with",
    "is",
    "are",
}

ROLE_WEIGHTS = {
    ArticleEntity.ROLE_MAIN: 2.0,
    ArticleEntity.ROLE_MENTIONED: 1.0,
    ArticleEntity.ROLE_AUTHOR: 1.2,
    ArticleEntity.ROLE_TARGET: 1.2,
}

TOKEN_PATTERN = re.compile(r"[a-z0-9\u0600-\u06ff]+")



def _normalize_text(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[\u064b-\u065f\u0670\u0640]", "", value)
    replacements = {
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ة": "ه",
        "ؤ": "و",
        "أ": "ا",
        "إ": "ا",
        "ۀ": "ه",
        "‌": " ",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    value = re.sub(r"\s+", " ", value)
    return value



def normalize_title_tokens(title: str) -> list[str]:
    """Return deterministic normalized title tokens (unigrams + bigrams)."""
    weights = _title_token_weights(title)
    return sorted(weights.keys())



def _title_token_weights(title: str) -> dict[str, float]:
    text = _normalize_text(title)
    raw_tokens = TOKEN_PATTERN.findall(text)

    tokens: list[str] = []
    for token in raw_tokens:
        if len(token) < 2:
            continue
        if token in PERSIAN_STOPWORDS or token in ENGLISH_STOPWORDS:
            continue
        tokens.append(token)

    token_weights: dict[str, float] = defaultdict(float)
    for token in tokens:
        token_weights[token] += 1.0

    for i in range(len(tokens) - 1):
        bigram = f"{tokens[i]}_{tokens[i + 1]}"
        token_weights[bigram] += 2.0

    return dict(token_weights)



def _weighted_jaccard(map_a: dict, map_b: dict) -> float:
    if not map_a and not map_b:
        return 0.0

    keys = set(map_a.keys()) | set(map_b.keys())
    numerator = sum(min(float(map_a.get(key, 0.0)), float(map_b.get(key, 0.0))) for key in keys)
    denominator = sum(max(float(map_a.get(key, 0.0)), float(map_b.get(key, 0.0))) for key in keys)

    if denominator <= 0:
        return 0.0
    return float(numerator / denominator)



def _jaccard(set_a: set, set_b: set) -> float:
    if not set_a and not set_b:
        return 0.0
    union_size = len(set_a | set_b)
    if union_size == 0:
        return 0.0
    return len(set_a & set_b) / union_size



def _time_similarity(published_a, published_b) -> float:
    if not published_a or not published_b:
        return 0.0
    days_diff = abs((published_a.date() - published_b.date()).days)
    return float(math.exp(-days_diff / 90.0))



def _clamp_01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))



def _resolve_article(article_identifier) -> Article:
    queryset = Article.objects.filter(status=Article.STATUS_PUBLISHED)

    if isinstance(article_identifier, Article):
        if article_identifier.status != Article.STATUS_PUBLISHED:
            raise Article.DoesNotExist("Article is not published.")
        return article_identifier

    if isinstance(article_identifier, int):
        return queryset.get(pk=article_identifier)

    if isinstance(article_identifier, str):
        raw = article_identifier.strip()
        if raw.isdigit():
            return queryset.get(pk=int(raw))
        return queryset.get(slug=raw)

    raise TypeError("article_identifier must be an Article, int, or slug string")



def _collect_source_feature_ids(article_id: int) -> tuple[set[int], set[int], set[int]]:
    category_ids = set(
        ArticleCategory.objects.filter(article_id=article_id).values_list("category_id", flat=True)
    )
    entity_ids = set(
        ArticleEntity.objects.filter(article_id=article_id).values_list("entity_id", flat=True)
    )
    tag_ids = set(
        ArticleTag.objects.filter(article_id=article_id).values_list("tag_id", flat=True)
    )
    return category_ids, entity_ids, tag_ids



def _generate_candidate_ids(
    source_article: Article,
    *,
    max_candidates: int,
    horizon_days: int,
) -> list[int]:
    now = timezone.now()

    category_ids, entity_ids, tag_ids = _collect_source_feature_ids(source_article.id)

    base_queryset = Article.objects.filter(status=Article.STATUS_PUBLISHED).exclude(pk=source_article.id)

    if horizon_days and horizon_days > 0:
        cutoff = now - timedelta(days=horizon_days)
        base_queryset = base_queryset.filter(published_at__gte=cutoff)

    limit_per_source = max(max_candidates * 2, max_candidates + 100)

    candidate_ids: set[int] = set()
    source_hits: dict[int, dict[str, int]] = defaultdict(lambda: {"cat": 0, "ent": 0, "tag": 0, "type": 0})

    def add_candidates(queryset, hit_key: str):
        ids = list(queryset.order_by("-published_at").values_list("id", flat=True).distinct()[:limit_per_source])
        for candidate_id in ids:
            candidate_ids.add(candidate_id)
            source_hits[candidate_id][hit_key] += 1

    if category_ids:
        add_candidates(base_queryset.filter(article_categories__category_id__in=category_ids), "cat")

    if entity_ids:
        add_candidates(base_queryset.filter(article_entities__entity_id__in=entity_ids), "ent")

    if tag_ids:
        add_candidates(base_queryset.filter(article_tags__tag_id__in=tag_ids), "tag")

    add_candidates(base_queryset.filter(content_type=source_article.content_type), "type")

    if not candidate_ids:
        return list(base_queryset.order_by("-published_at").values_list("id", flat=True)[:max_candidates])

    if len(candidate_ids) <= max_candidates:
        return list(candidate_ids)

    candidate_id_list = list(candidate_ids)

    entity_overlap: dict[int, int] = {}
    if entity_ids:
        for row in (
            ArticleEntity.objects.filter(article_id__in=candidate_id_list, entity_id__in=entity_ids)
            .values("article_id")
            .annotate(count=Count("entity_id"))
        ):
            entity_overlap[row["article_id"]] = int(row["count"])

    category_overlap: dict[int, int] = {}
    if category_ids:
        for row in (
            ArticleCategory.objects.filter(article_id__in=candidate_id_list, category_id__in=category_ids)
            .values("article_id")
            .annotate(count=Count("category_id"))
        ):
            category_overlap[row["article_id"]] = int(row["count"])

    published_at_map = {
        row["id"]: row["published_at"]
        for row in Article.objects.filter(id__in=candidate_id_list).values("id", "published_at")
    }

    def sort_key(candidate_id: int):
        hit = source_hits.get(candidate_id, {})
        hit_score = (
            hit.get("ent", 0) * 4
            + hit.get("cat", 0) * 3
            + hit.get("tag", 0) * 2
            + hit.get("type", 0)
        )
        return (
            entity_overlap.get(candidate_id, 0),
            category_overlap.get(candidate_id, 0),
            hit_score,
            published_at_map.get(candidate_id) or datetime.min.replace(tzinfo=dt_timezone.utc),
            candidate_id,
        )

    ranked = sorted(candidate_id_list, key=sort_key, reverse=True)
    return ranked[:max_candidates]



def _load_article_features(article_ids: list[int]) -> dict[int, dict]:
    article_rows = Article.objects.filter(id__in=article_ids).values(
        "id",
        "slug",
        "title",
        "content_type",
        "published_at",
    )

    features: dict[int, dict] = {}
    for row in article_rows:
        features[row["id"]] = {
            "id": row["id"],
            "slug": row["slug"],
            "content_type": row["content_type"],
            "published_at": row["published_at"],
            "categories": {},
            "entities": {},
            "tags": set(),
            "category_slugs": set(),
            "entity_slugs": set(),
            "tag_slugs": set(),
            "title_weights": _title_token_weights(row["title"]),
        }

    category_rows = ArticleCategory.objects.filter(article_id__in=features.keys()).values(
        "article_id",
        "category_id",
        "is_primary",
        "weight",
        "category__slug",
    )
    for row in category_rows:
        article_feature = features.get(row["article_id"])
        if not article_feature:
            continue
        base_w = float(row.get("weight") or 1.0)
        weight = base_w * (1.5 if row["is_primary"] else 1.0)
        article_feature["categories"][row["category_id"]] = max(
            article_feature["categories"].get(row["category_id"], 0.0),
            weight,
        )
        if row["category__slug"]:
            article_feature["category_slugs"].add(row["category__slug"])

    entity_rows = ArticleEntity.objects.filter(article_id__in=features.keys()).values(
        "article_id",
        "entity_id",
        "role",
        "importance",
        "entity__slug",
    )
    for row in entity_rows:
        article_feature = features.get(row["article_id"])
        if not article_feature:
            continue
        role_weight = ROLE_WEIGHTS.get(row["role"], 1.0)
        importance = float(row.get("importance") or 1.0)
        weight = max(0.0, role_weight * importance)
        article_feature["entities"][row["entity_id"]] = article_feature["entities"].get(row["entity_id"], 0.0) + weight
        if row["entity__slug"]:
            article_feature["entity_slugs"].add(row["entity__slug"])

    tag_rows = ArticleTag.objects.filter(article_id__in=features.keys()).values(
        "article_id",
        "tag_id",
        "tag__slug",
    )
    for row in tag_rows:
        article_feature = features.get(row["article_id"])
        if not article_feature:
            continue
        article_feature["tags"].add(row["tag_id"])
        if row["tag__slug"]:
            article_feature["tag_slugs"].add(row["tag__slug"])

    return features



def _similarity_signals(source: dict, candidate: dict) -> tuple[float, dict]:
    s_cat = _weighted_jaccard(source["categories"], candidate["categories"])
    s_ent = _weighted_jaccard(source["entities"], candidate["entities"])
    s_tag = _jaccard(source["tags"], candidate["tags"])
    s_title = _weighted_jaccard(source["title_weights"], candidate["title_weights"])
    s_time = _time_similarity(source["published_at"], candidate["published_at"])
    s_type = 1.0 if source["content_type"] == candidate["content_type"] else 0.0

    score = (
        settings.RELATIONS_WEIGHT_ENTITY * s_ent
        + settings.RELATIONS_WEIGHT_CATEGORY * s_cat
        + settings.RELATIONS_WEIGHT_TITLE * s_title
        + settings.RELATIONS_WEIGHT_TAG * s_tag
        + settings.RELATIONS_WEIGHT_TIME * s_time
        + settings.RELATIONS_WEIGHT_TYPE * s_type
    )
    score = _clamp_01(score)

    signals = {
        "S_cat": round(s_cat, 6),
        "S_ent": round(s_ent, 6),
        "S_title": round(s_title, 6),
        "S_tag": round(s_tag, 6),
        "S_time": round(s_time, 6),
        "S_type": round(s_type, 6),
        "shared": {
            "categories": sorted(source["category_slugs"] & candidate["category_slugs"]),
            "entities": sorted(source["entity_slugs"] & candidate["entity_slugs"]),
            "tags": sorted(source["tag_slugs"] & candidate["tag_slugs"]),
        },
    }

    return score, signals



def _serialize_article_summary(article: Article) -> dict:
    return {
        "id": article.id,
        "slug": article.slug,
        "title": article.title,
        "url": article.get_absolute_url(),
        "hero_image": article.hero_image or None,
        "thumbnail": article.thumbnail or None,
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "content_type": article.content_type,
        "is_team_pick": article.is_team_pick,
    }



def build_relations_for_article(
    article_id,
    *,
    top_n: int = 30,
    max_candidates: int = 600,
    horizon_days: int = 365,
    algo_version: str = "v1",
) -> list[dict]:
    top_n = int(top_n or settings.RELATIONS_TOP_N)
    max_candidates = int(max_candidates or settings.RELATIONS_MAX_CANDIDATES)
    horizon_days = int(horizon_days or settings.RELATIONS_HORIZON_DAYS)
    algo_version = algo_version or settings.RELATIONS_ALGO_VERSION

    source_article = _resolve_article(article_id)

    candidate_ids = _generate_candidate_ids(
        source_article,
        max_candidates=max_candidates,
        horizon_days=horizon_days,
    )

    if not candidate_ids:
        ArticleRelation.objects.filter(
            algo_version=algo_version,
        ).filter(
            Q(article_a_id=source_article.id) | Q(article_b_id=source_article.id)
        ).delete()
        return []

    feature_ids = [source_article.id] + candidate_ids
    features = _load_article_features(feature_ids)

    source_features = features.get(source_article.id)
    if not source_features:
        return []

    scored_candidates = []
    for candidate_id in candidate_ids:
        candidate_features = features.get(candidate_id)
        if not candidate_features:
            continue

        score, signals = _similarity_signals(source_features, candidate_features)
        if score < settings.RELATIONS_MIN_SCORE:
            continue

        scored_candidates.append(
            {
                "article_id": candidate_id,
                "score": round(score, 6),
                "signals": signals,
                "published_at": candidate_features["published_at"],
                "slug": candidate_features["slug"],
            }
        )

    scored_candidates.sort(
        key=lambda row: (
            row["score"],
            row["published_at"] or datetime.min.replace(tzinfo=dt_timezone.utc),
            row["article_id"],
        ),
        reverse=True,
    )

    top_candidates = scored_candidates[:top_n]

    existing_relations = ArticleRelation.objects.filter(
        algo_version=algo_version,
    ).filter(
        Q(article_a_id=source_article.id) | Q(article_b_id=source_article.id)
    )

    existing_by_other_id: dict[int, ArticleRelation] = {}
    for relation in existing_relations:
        other_id = relation.article_b_id if relation.article_a_id == source_article.id else relation.article_a_id
        existing_by_other_id[other_id] = relation

    kept_other_ids = set()

    for row in top_candidates:
        other_id = row["article_id"]
        kept_other_ids.add(other_id)

        existing = existing_by_other_id.get(other_id)
        if existing:
            existing.score = row["score"]
            existing.signals = row["signals"]
            existing.algo_version = algo_version
            existing.save()
            continue

        pair_a, pair_b = normalize_article_pair(source_article.id, other_id)
        try:
            ArticleRelation.objects.create(
                article_a_id=pair_a,
                article_b_id=pair_b,
                score=row["score"],
                signals=row["signals"],
                algo_version=algo_version,
            )
        except IntegrityError:
            ArticleRelation.objects.filter(
                article_a_id=pair_a,
                article_b_id=pair_b,
            ).update(
                score=row["score"],
                signals=row["signals"],
                algo_version=algo_version,
            )

    stale_relation_ids = [
        relation.id
        for other_id, relation in existing_by_other_id.items()
        if other_id not in kept_other_ids
    ]
    if stale_relation_ids:
        ArticleRelation.objects.filter(id__in=stale_relation_ids).delete()

    return top_candidates



def rebuild_relations_for_recent(
    days: int = 30,
    top_n: int = 30,
    max_candidates: int = 600,
    horizon_days: int = 365,
    algo_version: str = "v1",
) -> int:
    days = int(days or 30)
    algo_version = algo_version or settings.RELATIONS_ALGO_VERSION

    cutoff = timezone.now() - timedelta(days=max(days, 1))
    article_ids = list(
        Article.objects.filter(
            status=Article.STATUS_PUBLISHED,
            published_at__gte=cutoff,
        )
        .order_by("-published_at")
        .values_list("id", flat=True)
    )

    rebuilt_count = 0
    for article_id in article_ids:
        build_relations_for_article(
            article_id,
            top_n=top_n,
            max_candidates=max_candidates,
            horizon_days=horizon_days,
            algo_version=algo_version,
        )
        rebuilt_count += 1

    return rebuilt_count



def _fallback_related_articles(source_article: Article, *, limit: int, exclude_ids: set[int]) -> list[dict]:
    remaining = max(limit, 0)
    if remaining == 0:
        return []

    result: list[Article] = []
    seen_ids = set(exclude_ids)

    category_ids = list(
        ArticleCategory.objects.filter(article_id=source_article.id).values_list("category_id", flat=True)
    )
    entity_ids = list(
        ArticleEntity.objects.filter(article_id=source_article.id).values_list("entity_id", flat=True)
    )

    base_queryset = Article.objects.filter(status=Article.STATUS_PUBLISHED).exclude(id=source_article.id)

    if category_ids:
        for article in (
            base_queryset.filter(article_categories__category_id__in=category_ids)
            .exclude(id__in=seen_ids)
            .distinct()
            .order_by("-published_at")[:remaining]
        ):
            result.append(article)
            seen_ids.add(article.id)

    if len(result) < limit and entity_ids:
        needed = limit - len(result)
        for article in (
            base_queryset.filter(article_entities__entity_id__in=entity_ids)
            .exclude(id__in=seen_ids)
            .distinct()
            .order_by("-published_at")[:needed]
        ):
            result.append(article)
            seen_ids.add(article.id)

    if len(result) < limit:
        needed = limit - len(result)
        for article in base_queryset.exclude(id__in=seen_ids).order_by("-published_at")[:needed]:
            result.append(article)
            seen_ids.add(article.id)

    return [
        {
            **_serialize_article_summary(article),
            "relation_score": 0.0,
            "reason": {"type": "fallback"},
        }
        for article in result[:limit]
    ]



def get_related_articles(
    article,
    limit: int = 10,
    algo_version: str | None = None,
    include_signals: bool = False,
) -> list[dict]:
    source_article = _resolve_article(article)
    algo_version = algo_version or settings.RELATIONS_ALGO_VERSION

    relation_rows = (
        ArticleRelation.objects.filter(algo_version=algo_version)
        .filter(Q(article_a_id=source_article.id) | Q(article_b_id=source_article.id))
        .select_related("article_a", "article_b")
        .order_by("-score")[: max(limit * 4, 20)]
    )

    related_items: list[dict] = []
    seen_ids: set[int] = {source_article.id}

    for relation in relation_rows:
        other_article = relation.article_b if relation.article_a_id == source_article.id else relation.article_a
        if other_article.id in seen_ids:
            continue
        if other_article.status != Article.STATUS_PUBLISHED:
            continue

        seen_ids.add(other_article.id)
        item = {
            **_serialize_article_summary(other_article),
            "relation_score": round(float(relation.score), 6),
            "reason": {"type": "graph", "algo_version": relation.algo_version},
        }
        if include_signals:
            item["signals"] = relation.signals

        related_items.append(item)

        if len(related_items) >= limit:
            return related_items

    fallback_items = _fallback_related_articles(
        source_article,
        limit=limit - len(related_items),
        exclude_ids=seen_ids,
    )
    return related_items + fallback_items
