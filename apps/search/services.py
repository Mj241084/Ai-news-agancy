from __future__ import annotations

import re
from datetime import datetime, timezone
from functools import reduce
from operator import or_

from django.conf import settings
from django.db.models import Q

from apps.content.models import Article, ArticleCategory
from apps.content.services import get_published_queryset
from apps.interactions.services import get_popular_article_scores

SEARCH_TOKEN_SPLIT_RE = re.compile(r"[\s\u200c]+")
SEARCH_CLEAN_RE = re.compile(r"[^\w\s\u0600-\u06ff-]")

SORT_KEYWORDS = {
    "latest": {"جدیدترین", "آخرین", "تازه"},
    "popular": {"پرطرفدار", "محبوب", "ترند"},
}

TYPE_KEYWORDS = {
    "articles": {"مقاله", "مقالات", "مجله", "مجلات"},
    "news": {"خبر", "اخبار"},
}

TEAM_KEYWORDS = {"پیشنهادی", "منتخب", "ویژه"}


def normalize_search_text(text: str) -> str:
    text = (text or "").strip().lower()
    text = SEARCH_CLEAN_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    return [token for token in SEARCH_TOKEN_SPLIT_RE.split(text) if token]


def _build_phrase_plan(tokens: list[str]) -> dict:
    if not tokens:
        return {
            "phrases": [],
            "tokens": [],
            "steps": [],
        }

    phrases: list[str] = []
    seen = set()

    full_phrase = " ".join(tokens)
    phrases.append(full_phrase)
    seen.add(full_phrase)

    max_ngram = min(len(tokens), 4)
    chunk_phrases = []
    for n in range(max_ngram, 1, -1):
        for idx in range(0, len(tokens) - n + 1):
            phrase = " ".join(tokens[idx : idx + n])
            if phrase in seen:
                continue
            seen.add(phrase)
            chunk_phrases.append(phrase)

    token_phrases = []
    for token in sorted(tokens, key=len, reverse=True):
        if token in seen or len(token) < 2:
            continue
        seen.add(token)
        token_phrases.append(token)

    phrases.extend(chunk_phrases)

    return {
        "phrases": phrases,
        "tokens": token_phrases,
        "steps": [
            {"stage": "full", "terms": [full_phrase]},
            {"stage": "chunks", "terms": chunk_phrases},
            {"stage": "tokens", "terms": token_phrases},
        ],
    }


def parse_search_query(q: str) -> tuple[str, dict, dict]:
    normalized = normalize_search_text(q)
    tokens = _tokenize(normalized)

    filters = {
        "type": "all",
        "sort": "latest",
        "team_pick": False,
    }

    cleaned_tokens = []
    for token in tokens:
        if token in SORT_KEYWORDS["latest"]:
            filters["sort"] = "latest"
            continue
        if token in SORT_KEYWORDS["popular"]:
            filters["sort"] = "popular"
            continue
        if token in TYPE_KEYWORDS["articles"]:
            filters["type"] = "articles"
            continue
        if token in TYPE_KEYWORDS["news"]:
            filters["type"] = "news"
            continue
        if token in TEAM_KEYWORDS:
            filters["team_pick"] = True
            filters["sort"] = "team"
            continue
        cleaned_tokens.append(token)

    clean_text = " ".join(cleaned_tokens)
    plan = _build_phrase_plan(cleaned_tokens)
    plan["raw_query"] = q
    plan["clean_query"] = clean_text
    return clean_text, filters, plan


def _apply_search_filters(queryset, filters: dict):
    if filters.get("type") == "news":
        queryset = queryset.filter(content_type=Article.CONTENT_SHORT_NEWS)
    elif filters.get("type") == "articles":
        queryset = queryset.filter(content_type__in=[Article.CONTENT_POST, Article.CONTENT_ARTICLE])

    if filters.get("team_pick") or filters.get("sort") == "team":
        queryset = queryset.filter(is_team_pick=True)

    return queryset


def _build_candidate_query(phrases: list[str], tokens: list[str]) -> Q | None:
    terms = []
    terms.extend(phrases[:14])
    terms.extend(tokens[:20])
    terms = [term for term in terms if term and len(term) >= 2]

    if not terms:
        return None

    conditions = [
        Q(title__icontains=term) | Q(excerpt__icontains=term) | Q(body__icontains=term)
        for term in terms
    ]
    return reduce(or_, conditions)


def _score_article(article: Article, plan: dict) -> float:
    title = (article.title or "").lower()
    excerpt = (article.excerpt or "").lower()
    body = (article.body or "").lower()

    total_score = 0.0

    for idx, phrase in enumerate(plan.get("phrases", [])):
        words = len(phrase.split())
        specificity = max(words, 1)
        stage_weight = max(90 - (idx * 4), 20)

        if phrase in title:
            total_score += stage_weight * 3.0 * specificity
        if phrase in excerpt:
            total_score += stage_weight * 2.0 * specificity
        if phrase in body:
            total_score += stage_weight * 1.0 * specificity

    for token in plan.get("tokens", []):
        token_weight = max(len(token), 1)
        if token in title:
            total_score += 16 + token_weight
        if token in excerpt:
            total_score += 8 + (token_weight * 0.5)
        if token in body:
            total_score += 4 + (token_weight * 0.25)

    return total_score


def _sort_ranked_items(items: list[dict], filters: dict):
    def _published_sort_value(item: dict):
        value = item.get("published_at")
        if value is None:
            return datetime.min.replace(tzinfo=timezone.utc)
        return value

    sort_mode = filters.get("sort", "latest")

    if sort_mode == "popular":
        items.sort(
            key=lambda item: (
                item["popularity_score"],
                item["relevance_score"],
                _published_sort_value(item),
            ),
            reverse=True,
        )
        return

    if sort_mode == "team":
        items.sort(
            key=lambda item: (
                item["is_team_pick"],
                _published_sort_value(item),
                item["relevance_score"],
            ),
            reverse=True,
        )
        return

    items.sort(
        key=lambda item: (
            _published_sort_value(item),
            item["relevance_score"],
        ),
        reverse=True,
    )


def run_search(plan: dict, filters: dict, *, page: int = 1, page_size: int | None = None) -> dict:
    page_size = page_size or settings.SEARCH_PAGE_SIZE
    page = max(int(page or 1), 1)

    phrases = plan.get("phrases", [])
    tokens = plan.get("tokens", [])

    candidate_query = _build_candidate_query(phrases, tokens)
    if candidate_query is None:
        return {
            "query": plan.get("raw_query", ""),
            "filters": {"type": filters.get("type", "all"), "sort": filters.get("sort", "latest")},
            "page": page,
            "page_size": page_size,
            "total": 0,
            "items": [],
        }

    queryset = _apply_search_filters(get_published_queryset(), filters)
    queryset = queryset.filter(candidate_query).only(
        "id",
        "title",
        "slug",
        "excerpt",
        "body",
        "published_at",
        "content_type",
        "is_team_pick",
        "hero_image",
        "thumbnail",
    )

    candidates = list(queryset.order_by("-published_at")[: settings.SEARCH_CANDIDATE_LIMIT])
    if not candidates:
        return {
            "query": plan.get("raw_query", ""),
            "filters": {"type": filters.get("type", "all"), "sort": filters.get("sort", "latest")},
            "page": page,
            "page_size": page_size,
            "total": 0,
            "items": [],
        }

    candidate_ids = [article.id for article in candidates]
    popularity_map = get_popular_article_scores(article_ids=candidate_ids)
    category_map: dict[int, list[dict]] = {article_id: [] for article_id in candidate_ids}
    for row in (
        ArticleCategory.objects.filter(article_id__in=candidate_ids)
        .values("article_id", "category__title", "category__slug")
    ):
        category_map.setdefault(row["article_id"], []).append(
            {
                "name": row["category__title"],
                "title": row["category__title"],
                "slug": row["category__slug"],
            }
        )

    ranked_items = []
    for article in candidates:
        relevance_score = _score_article(article, plan)
        ranked_items.append(
            {
                "id": article.id,
                "title": article.title,
                "slug": article.slug,
                "url": article.get_absolute_url(),
                "excerpt": article.excerpt,
                "published_at": article.published_at,
                "content_type": article.content_type,
                "is_team_pick": article.is_team_pick,
                "hero_image": article.hero_image or None,
                "thumbnail": article.thumbnail or None,
                "read_time": max(1, int(len((article.body or "").split()) / 220) + 1),
                "categories": category_map.get(article.id, []),
                "relevance_score": round(relevance_score, 2),
                "popularity_score": round(float(popularity_map.get(article.id, 0)), 2),
                "view_count": int(popularity_map.get(article.id, 0)),
            }
        )

    _sort_ranked_items(ranked_items, filters)

    total = len(ranked_items)
    start = (page - 1) * page_size
    end = start + page_size

    paged_items = ranked_items[start:end]

    for item in paged_items:
        item.pop("relevance_score", None)

    return {
        "query": plan.get("raw_query", ""),
        "filters": {"type": filters.get("type", "all"), "sort": filters.get("sort", "latest")},
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": paged_items,
    }


class SearchService:
    @staticmethod
    def parse_search_query(q: str) -> tuple[str, dict, dict]:
        return parse_search_query(q)

    @staticmethod
    def run_search(plan: dict, filters: dict, *, page: int = 1, page_size: int | None = None) -> dict:
        return run_search(plan, filters, page=page, page_size=page_size)
