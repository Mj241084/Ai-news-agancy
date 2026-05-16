from __future__ import annotations

from utils.caching import make_cache_key


def category_index_key(v: str = "v1") -> str:
    return make_cache_key("taxonomy:category-index", v=v)


def category_detail_key(
    slug: str,
    page: int,
    sort: str,
    type: str,
    sub: int,
    v: str = "v1",
) -> str:
    return make_cache_key(
        "taxonomy:category-detail",
        v=v,
        slug=slug,
        page=page,
        sort=sort,
        type=type,
        sub=sub,
    )


def tag_detail_key(
    slug: str,
    page: int,
    sort: str,
    type: str,
    v: str = "v1",
) -> str:
    return make_cache_key(
        "taxonomy:tag-detail",
        v=v,
        slug=slug,
        page=page,
        sort=sort,
        type=type,
    )


def entity_detail_key(
    type: str,
    slug: str,
    page: int,
    v: str = "v1",
) -> str:
    return make_cache_key(
        "taxonomy:entity-detail",
        v=v,
        type=type,
        slug=slug,
        page=page,
    )

