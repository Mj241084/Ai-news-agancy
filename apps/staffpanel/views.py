from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum, Avg
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView
from django.forms import inlineformset_factory

from apps.content.cache_invalidation import invalidate_article_cache, invalidate_listing_caches
from apps.content.models import Article, ArticleCategory, ArticleEntity, ArticleComment, ArticleSource, Source
from apps.content.utils import render_markdown_safe
from apps.entities.models import Entity, RankingEntry, RankingList
from apps.editorial.models import PromptTemplate, WritingRuleSet
from apps.interactions.models import Poll, PollAnswer, PollChoice, PollQuestion, DailyArticleInteraction, ArticleRating
from apps.staffpanel.forms import (
    ArticleStaffForm,
    ArticleCategoryFormSet,
    ArticleEntityFormSet,
    ArticleSourceFormSet,
    CategoryStaffForm,
    EntityStaffForm,
    PollChoiceStaffForm,
    PollQuestionStaffForm,
    PollStaffForm,
    TagStaffForm,
    RankingEntryStaffForm,
    RankingListStaffForm,
    PromptTemplateStaffForm,
    WritingRuleSetStaffForm,
    SourceStaffForm,
)
from apps.staffpanel.mixins import (
    ContentEditorRequiredMixin,
    EditorialAdminRequiredMixin,
    StaffRequiredMixin,
    user_in_group,
    GROUP_EDITORIAL_ADMINS,
)
from apps.taxonomy.cache_invalidation import (
    invalidate_taxonomy_on_category_change,
    invalidate_taxonomy_on_entity_change,
    invalidate_taxonomy_on_tag_change,
    invalidate_entity_detail_caches_for_slug,
)
from apps.taxonomy.models import Category, Tag
from utils.caching import make_cache_key


ACTIVE_POLL_HTML_CACHE_KEY = make_cache_key("polls:active:html")


def _invalidate_active_poll_cache() -> None:
    cache.delete(ACTIVE_POLL_HTML_CACHE_KEY)


class NextUrlMixin:
    next_param = "next"
    success_url_name: str | None = None

    def _resolve_next_url(self):
        next_url = (
            self.request.POST.get(self.next_param)
            or self.request.GET.get(self.next_param)
            or ""
        ).strip()
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={self.request.get_host()},
            require_https=self.request.is_secure(),
        ):
            return next_url
        return ""

    def get_success_url(self):
        next_url = self._resolve_next_url()
        if next_url:
            return next_url
        if self.success_url_name:
            return reverse(self.success_url_name)
        return super().get_success_url()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["next_url"] = self._resolve_next_url()
        return context


class DashboardView(ContentEditorRequiredMixin, TemplateView):
    template_name = "staffpanel/dashboard.html"

    def dispatch(self, request, *args, **kwargs):
        # Content editors land on Articles list (keeps navigation simple).
        if user_in_group(request.user, "content_editors") and not user_in_group(
            request.user, GROUP_EDITORIAL_ADMINS
        ):
            return redirect("staffpanel:article-list")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queryset = Article.objects.all()

        context.update(
            {
                "total_count": queryset.count(),
                "draft_count": queryset.filter(status=Article.STATUS_DRAFT).count(),
                "published_count": queryset.filter(status=Article.STATUS_PUBLISHED).count(),
                "team_pick_count": queryset.filter(is_team_pick=True).count(),
                "poll_count": Poll.objects.count(),
                "recent_articles": queryset.order_by("-updated_at")[:8],
            }
        )
        return context


class ArticleListView(ContentEditorRequiredMixin, ListView):
    model = Article
    template_name = "staffpanel/article_list.html"
    context_object_name = "articles"
    paginate_by = 20

    def get_queryset(self):
        queryset = Article.objects.all().order_by("-updated_at")

        status_filter = (self.request.GET.get("status") or "all").strip().lower()
        type_filter = (self.request.GET.get("type") or "all").strip().lower()
        team_filter = (self.request.GET.get("team") or "").strip()
        query_text = (self.request.GET.get("q") or "").strip()

        if status_filter in {Article.STATUS_DRAFT, Article.STATUS_PUBLISHED}:
            queryset = queryset.filter(status=status_filter)

        valid_types = {choice[0] for choice in Article.CONTENT_TYPE_CHOICES}
        if type_filter in valid_types:
            queryset = queryset.filter(content_type=type_filter)

        if team_filter == "1":
            queryset = queryset.filter(is_team_pick=True)

        if query_text:
            queryset = queryset.filter(Q(title__icontains=query_text) | Q(slug__icontains=query_text))

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "filters": {
                    "status": (self.request.GET.get("status") or "all").strip().lower(),
                    "type": (self.request.GET.get("type") or "all").strip().lower(),
                    "team": (self.request.GET.get("team") or "").strip(),
                    "q": (self.request.GET.get("q") or "").strip(),
                },
                "status_options": [
                    ("all", "همه"),
                    (Article.STATUS_DRAFT, "پیش‌نویس"),
                    (Article.STATUS_PUBLISHED, "منتشر شده"),
                ],
                "type_options": [
                    ("all", "همه"),
                    (Article.CONTENT_SHORT_NEWS, "خبر کوتاه"),
                    (Article.CONTENT_POST, "پست"),
                    (Article.CONTENT_ARTICLE, "مقاله"),
                ],
            }
        )

        # Lightweight per-page stats (keeps list fast on SQLite too)
        page_obj = context.get("page_obj")
        if page_obj and getattr(page_obj, "object_list", None):
            articles = list(page_obj.object_list)
            article_ids = [a.id for a in articles if getattr(a, "id", None)]
            if article_ids:
                since = timezone.localdate() - timedelta(days=30)

                interaction_rows = (
                    DailyArticleInteraction.objects.filter(article_id__in=article_ids, date__gte=since)
                    .values("article_id")
                    .annotate(views_30d=Sum("views"), shares_30d=Sum("shares"))
                )
                interaction_map = {r["article_id"]: r for r in interaction_rows}

                comment_rows = (
                    ArticleComment.objects.filter(article_id__in=article_ids, is_visible=True)
                    .values("article_id")
                    .annotate(comments=Count("id"))
                )
                comment_map = {r["article_id"]: r for r in comment_rows}

                rating_rows = (
                    ArticleRating.objects.filter(article_id__in=article_ids)
                    .values("article_id")
                    .annotate(rating_avg=Avg("value"), rating_count=Count("id"))
                )
                rating_map = {r["article_id"]: r for r in rating_rows}

                for a in articles:
                    base = {
                        "views_30d": 0,
                        "shares_30d": 0,
                        "comments": 0,
                        "rating_avg": None,
                        "rating_count": 0,
                    }
                    if a.id in interaction_map:
                        base["views_30d"] = int(interaction_map[a.id].get("views_30d") or 0)
                        base["shares_30d"] = int(interaction_map[a.id].get("shares_30d") or 0)
                    if a.id in comment_map:
                        base["comments"] = int(comment_map[a.id].get("comments") or 0)
                    if a.id in rating_map:
                        base["rating_avg"] = rating_map[a.id].get("rating_avg")
                        base["rating_count"] = int(rating_map[a.id].get("rating_count") or 0)
                    a.stats = base

        return context


class _ArticleFormsetMixin:
    def _get_previous_state(self) -> tuple[dict | None, set[int], set[int]]:
        if not getattr(self, "object", None) or not getattr(self.object, "pk", None):
            return None, set(), set()
        old_article = (
            Article.objects.filter(pk=self.object.pk)
            .only("slug", "status", "content_type", "is_team_pick")
            .first()
        )
        if not old_article:
            return None, set(), set()
        previous_state = {
            "slug": old_article.slug,
            "status": old_article.status,
            "content_type": old_article.content_type,
            "is_team_pick": old_article.is_team_pick,
        }
        previous_category_ids = set(
            ArticleCategory.objects.filter(article_id=old_article.id).values_list("category_id", flat=True)
        )
        previous_entity_ids = set(
            ArticleEntity.objects.filter(article_id=old_article.id).values_list("entity_id", flat=True)
        )
        return previous_state, previous_category_ids, previous_entity_ids

    def _build_formsets(self, *, form) -> tuple:
        # Use the same instance as the main form (may be unsaved for create).
        instance = form.instance
        category_formset = ArticleCategoryFormSet(self.request.POST or None, instance=instance)
        entity_formset = ArticleEntityFormSet(self.request.POST or None, instance=instance)
        source_formset = ArticleSourceFormSet(self.request.POST or None, instance=instance)
        return category_formset, entity_formset, source_formset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = context.get("form")
        if form is None:
            form = self.get_form()
            context["form"] = form
        category_formset, entity_formset, source_formset = self._build_formsets(form=form)
        context["category_formset"] = category_formset
        context["entity_formset"] = entity_formset
        context["source_formset"] = source_formset
        return context

    def _save_category_formset(self, article: Article, category_formset) -> None:
        # Avoid UniqueConstraint collisions by clearing primaries first
        ArticleCategory.objects.filter(article=article, is_primary=True).update(is_primary=False)

        category_formset.instance = article
        category_formset.save()

        # Ensure exactly one primary if any categories exist
        qs = ArticleCategory.objects.filter(article=article).order_by("-is_primary", "-weight", "id")
        if not qs.exists():
            return

        primary = qs.filter(is_primary=True).first()
        if not primary:
            primary = qs.first()
            ArticleCategory.objects.filter(pk=primary.pk).update(is_primary=True)
        # force others false
        ArticleCategory.objects.filter(article=article).exclude(pk=primary.pk).update(is_primary=False)



    def _save_entity_formset(self, article: Article, entity_formset) -> None:
        """Save ArticleEntity formset safely (avoid collisions with the MAIN-entity constraint)."""
        entity_formset.instance = article
        instances = entity_formset.save(commit=False)

        # Delete removed rows
        for obj in getattr(entity_formset, 'deleted_objects', []):
            obj.delete()

        # Save non-main rows first, then main rows
        non_main = [obj for obj in instances if obj.role != ArticleEntity.ROLE_MAIN]
        main = [obj for obj in instances if obj.role == ArticleEntity.ROLE_MAIN]

        for obj in non_main:
            obj.article = article
            obj.save()

        for obj in main:
            obj.article = article
            obj.save()

        # Auto-pick one MAIN entity if none selected but entities exist
        qs = ArticleEntity.objects.filter(article=article)
        if qs.exists() and not qs.filter(role=ArticleEntity.ROLE_MAIN).exists():
            preferred = qs.filter(role__in=[ArticleEntity.ROLE_MENTIONED, ArticleEntity.ROLE_TARGET]).order_by('-importance', 'id').first()
            if not preferred:
                preferred = qs.order_by('-importance', 'id').first()
            if preferred:
                # Avoid accidental duplicate (article, entity, role)
                if not ArticleEntity.objects.filter(article=article, entity_id=preferred.entity_id, role=ArticleEntity.ROLE_MAIN).exists():
                    ArticleEntity.objects.filter(pk=preferred.pk).update(role=ArticleEntity.ROLE_MAIN)

    def _invalidate_entity_detail_caches(self, *, article: Article, previous_entity_ids: set[int] | None = None) -> None:
        current_ids = set(ArticleEntity.objects.filter(article=article).values_list('entity_id', flat=True))
        affected = set(previous_entity_ids or set()) | current_ids
        if not affected:
            return
        for row in Entity.objects.filter(id__in=affected).values('type', 'slug'):
            invalidate_entity_detail_caches_for_slug(row['type'], row['slug'])
    def _save_source_formset(self, article: Article, source_formset) -> None:
        source_formset.instance = article
        source_formset.save()


class ArticleCreateView(ContentEditorRequiredMixin, NextUrlMixin, _ArticleFormsetMixin, CreateView):
    model = Article
    form_class = ArticleStaffForm
    template_name = "staffpanel/article_form.html"
    success_url_name = "staffpanel:article-list"

    def post(self, request, *args, **kwargs):
        self.object = None
        form = self.get_form()
        category_formset, entity_formset, source_formset = self._build_formsets(form=form)
        if form.is_valid() and category_formset.is_valid() and entity_formset.is_valid() and source_formset.is_valid():
            return self._forms_valid(form, category_formset, entity_formset, source_formset)
        return self._forms_invalid(form, category_formset, entity_formset, source_formset)

    def _forms_valid(self, form, category_formset, entity_formset, source_formset):
        previous_state, previous_category_ids = None, set()
        with transaction.atomic():
            article = form.save(commit=True)
            self.object = article
            self._save_category_formset(article, category_formset)
            self._save_entity_formset(article, entity_formset)
            self._save_source_formset(article, source_formset)

        if article.status == Article.STATUS_PUBLISHED:
            invalidate_article_cache(article)
            invalidate_listing_caches(article, previous_category_ids=previous_category_ids, previous_is_team_pick=None)
            self._invalidate_entity_detail_caches(article=article, previous_entity_ids=set())

        messages.success(self.request, "مقاله با موفقیت ایجاد شد.")
        return redirect(self.get_success_url())

    def _forms_invalid(self, form, category_formset, entity_formset, source_formset):
        context = self.get_context_data(form=form)
        context["category_formset"] = category_formset
        context["entity_formset"] = entity_formset
        context["source_formset"] = source_formset
        return self.render_to_response(context)

    def get_success_url(self):
        if "_preview" in self.request.POST:
            return reverse("staffpanel:article-preview", kwargs={"pk": self.object.pk})
        if "_continue" in self.request.POST:
            return reverse("staffpanel:article-edit", kwargs={"pk": self.object.pk})
        return super().get_success_url()


class ArticleUpdateView(ContentEditorRequiredMixin, NextUrlMixin, _ArticleFormsetMixin, UpdateView):
    model = Article
    form_class = ArticleStaffForm
    template_name = "staffpanel/article_form.html"
    success_url_name = "staffpanel:article-list"

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        previous_state, previous_category_ids, previous_entity_ids = self._get_previous_state()
        form = self.get_form()
        category_formset, entity_formset, source_formset = self._build_formsets(form=form)

        if form.is_valid() and category_formset.is_valid() and entity_formset.is_valid() and source_formset.is_valid():
            return self._forms_valid(form, category_formset, entity_formset, source_formset, previous_state, previous_category_ids, previous_entity_ids)
        return self._forms_invalid(form, category_formset, entity_formset, source_formset)

    def _forms_valid(self, form, category_formset, entity_formset, source_formset, previous_state, previous_category_ids, previous_entity_ids):
        with transaction.atomic():
            article = form.save(commit=True)
            self.object = article
            self._save_category_formset(article, category_formset)
            self._save_entity_formset(article, entity_formset)
            self._save_source_formset(article, source_formset)

        was_published = previous_state and previous_state.get("status") == Article.STATUS_PUBLISHED
        is_published = article.status == Article.STATUS_PUBLISHED
        if is_published or was_published:
            invalidate_article_cache(article, previous_slug=previous_state.get("slug") if previous_state else None)
            invalidate_listing_caches(
                article,
                previous_category_ids=previous_category_ids,
                previous_is_team_pick=previous_state.get("is_team_pick") if previous_state else None,
            )
            self._invalidate_entity_detail_caches(article=article, previous_entity_ids=previous_entity_ids)

        messages.success(self.request, "مقاله با موفقیت ویرایش شد.")
        return redirect(self.get_success_url())

    def _forms_invalid(self, form, category_formset, entity_formset, source_formset):
        context = self.get_context_data(form=form)
        context["category_formset"] = category_formset
        context["entity_formset"] = entity_formset
        context["source_formset"] = source_formset
        return self.render_to_response(context)

    def get_success_url(self):
        if "_preview" in self.request.POST:
            return reverse("staffpanel:article-preview", kwargs={"pk": self.object.pk})
        if "_continue" in self.request.POST:
            return reverse("staffpanel:article-edit", kwargs={"pk": self.object.pk})
        return super().get_success_url()

class ArticlePreviewView(ContentEditorRequiredMixin, DetailView):
    model = Article
    template_name = "staffpanel/article_preview.html"
    context_object_name = "article"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        article = self.object

        context.update(
            {
                "rendered_body": render_markdown_safe(article.body),
                "category_links": article.article_categories.select_related("category").order_by("-is_primary", "-weight", "category__title"),
                "tag_links": article.article_tags.select_related("tag").order_by("tag__title"),
                "entity_links": article.article_entities.select_related("entity").order_by(
                    "role", "-importance", "entity__name"
                ),
                "source_links": article.article_sources.select_related("source").order_by("source__name"),
                "goals": list(getattr(article, "goals", []) or []),
                "public_url": article.get_absolute_url() if article.status == Article.STATUS_PUBLISHED else None,
            }
        )
        return context


class DraftListView(ContentEditorRequiredMixin, TemplateView):
    template_name = "staffpanel/draft_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        drafts_queryset = Article.objects.filter(status=Article.STATUS_DRAFT).order_by("-updated_at")

        paginator = Paginator(drafts_queryset, 20)
        page_number = self.request.GET.get("page", 1)
        page_obj = paginator.get_page(page_number)

        preview_article = None
        preview_raw = (self.request.GET.get("preview") or "").strip()
        if preview_raw.isdigit():
            preview_article = get_object_or_404(drafts_queryset, pk=int(preview_raw))
        elif page_obj.object_list:
            preview_article = page_obj.object_list[0]

        context.update(
            {
                "drafts": page_obj.object_list,
                "page_obj": page_obj,
                "preview_article": preview_article,
                "preview_rendered": render_markdown_safe(preview_article.body) if preview_article else "",
            }
        )
        return context


### NOTE:
# Deleting articles from staffpanel is intentionally disabled to avoid breaking indexed URLs.



class SourceListView(ContentEditorRequiredMixin, ListView):
    model = Source
    template_name = "staffpanel/source_list.html"
    context_object_name = "sources"
    paginate_by = 30

    def get_queryset(self):
        qs = Source.objects.all().order_by("name")
        active = (self.request.GET.get("active") or "").strip()
        q = (self.request.GET.get("q") or "").strip()
        if active == "1":
            qs = qs.filter(is_active=True)
        if active == "0":
            qs = qs.filter(is_active=False)
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(url__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filters"] = {
            "active": (self.request.GET.get("active") or "").strip(),
            "q": (self.request.GET.get("q") or "").strip(),
        }
        return context


class SourceCreateView(ContentEditorRequiredMixin, NextUrlMixin, CreateView):
    model = Source
    form_class = SourceStaffForm
    template_name = "staffpanel/source_form.html"
    success_url_name = "staffpanel:source-list"

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "منبع با موفقیت ایجاد شد.")
        return response


class SourceUpdateView(ContentEditorRequiredMixin, NextUrlMixin, UpdateView):
    model = Source
    form_class = SourceStaffForm
    template_name = "staffpanel/source_form.html"
    success_url_name = "staffpanel:source-list"

    def form_valid(self, form):
        response = super().form_valid(form)

        # Invalidate caches of articles that reference this source
        article_ids = list(
            ArticleSource.objects.filter(source=self.object).values_list("article_id", flat=True).distinct()
        )
        if article_ids:
            for article in Article.objects.filter(id__in=article_ids, status=Article.STATUS_PUBLISHED):
                invalidate_article_cache(article)

        messages.success(self.request, "منبع با موفقیت ویرایش شد.")
        return response

class CategoryListView(EditorialAdminRequiredMixin, ListView):
    model = Category
    template_name = "staffpanel/category_list.html"
    context_object_name = "categories"

    def get_queryset(self):
        qs = Category.objects.select_related("parent").order_by("order", "title")
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(slug__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["q"] = (self.request.GET.get("q") or "").strip()
        return context


class CategoryCreateView(EditorialAdminRequiredMixin, NextUrlMixin, CreateView):
    model = Category
    form_class = CategoryStaffForm
    template_name = "staffpanel/taxonomy_form.html"
    success_url_name = "staffpanel:category-list"

    def form_valid(self, form):
        response = super().form_valid(form)
        invalidate_taxonomy_on_category_change(self.object)
        messages.success(self.request, "دسته‌بندی ایجاد شد.")
        return response


class CategoryUpdateView(EditorialAdminRequiredMixin, NextUrlMixin, UpdateView):
    model = Category
    form_class = CategoryStaffForm
    template_name = "staffpanel/taxonomy_form.html"
    success_url_name = "staffpanel:category-list"

    def form_valid(self, form):
        previous = self.get_object()
        previous_slug = previous.slug
        previous_parent_id = previous.parent_id
        response = super().form_valid(form)
        invalidate_taxonomy_on_category_change(
            self.object,
            previous_slug=previous_slug,
            previous_parent_id=previous_parent_id,
        )
        messages.success(self.request, "دسته‌بندی ویرایش شد.")
        return response


class TagListView(ContentEditorRequiredMixin, ListView):
    model = Tag
    template_name = "staffpanel/tag_list.html"
    context_object_name = "tags"

    def get_queryset(self):
        qs = Tag.objects.order_by("title")
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(slug__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["q"] = (self.request.GET.get("q") or "").strip()
        return context


class TagCreateView(ContentEditorRequiredMixin, NextUrlMixin, CreateView):
    model = Tag
    form_class = TagStaffForm
    template_name = "staffpanel/taxonomy_form.html"
    success_url_name = "staffpanel:tag-list"

    def form_valid(self, form):
        response = super().form_valid(form)
        invalidate_taxonomy_on_tag_change(self.object)
        messages.success(self.request, "تگ ایجاد شد.")
        return response


class TagUpdateView(ContentEditorRequiredMixin, NextUrlMixin, UpdateView):
    model = Tag
    form_class = TagStaffForm
    template_name = "staffpanel/taxonomy_form.html"
    success_url_name = "staffpanel:tag-list"

    def form_valid(self, form):
        previous_slug = self.get_object().slug
        response = super().form_valid(form)
        invalidate_taxonomy_on_tag_change(self.object, previous_slug=previous_slug)
        messages.success(self.request, "تگ ویرایش شد.")
        return response


class EntityListView(ContentEditorRequiredMixin, ListView):
    model = Entity
    template_name = "staffpanel/entity_list.html"
    context_object_name = "entities"

    def get_queryset(self):
        qs = Entity.objects.order_by("name")
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(slug__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["q"] = (self.request.GET.get("q") or "").strip()
        return context


class EntityCreateView(ContentEditorRequiredMixin, NextUrlMixin, CreateView):
    model = Entity
    form_class = EntityStaffForm
    template_name = "staffpanel/taxonomy_form.html"
    success_url_name = "staffpanel:entity-list"

    def form_valid(self, form):
        response = super().form_valid(form)
        invalidate_taxonomy_on_entity_change(self.object)
        messages.success(self.request, "انتیتی ایجاد شد.")
        return response


class EntityUpdateView(ContentEditorRequiredMixin, NextUrlMixin, UpdateView):
    model = Entity
    form_class = EntityStaffForm
    template_name = "staffpanel/taxonomy_form.html"
    success_url_name = "staffpanel:entity-list"

    def form_valid(self, form):
        previous = self.get_object()
        previous_slug = previous.slug
        previous_type = previous.type
        response = super().form_valid(form)
        invalidate_taxonomy_on_entity_change(
            self.object,
            previous_slug=previous_slug,
            previous_type=previous_type,
        )
        messages.success(self.request, "انتیتی ویرایش شد.")
        return response


class CategoryDeleteView(EditorialAdminRequiredMixin, NextUrlMixin, DeleteView):
    model = Category
    template_name = "staffpanel/taxonomy_confirm_delete.html"
    success_url_name = "staffpanel:category-list"

    def post(self, request, *args, **kwargs):
        category = self.get_object()
        previous_slug = category.slug
        previous_parent_id = category.parent_id

        try:
            response = super().post(request, *args, **kwargs)
        except ProtectedError:
            messages.error(request, "دسته‌بندی به خاطر استفاده در محتوا یا نقش والد، قابل حذف نیست.")
            return redirect(self.get_success_url())

        invalidate_taxonomy_on_category_change(
            category,
            previous_slug=previous_slug,
            previous_parent_id=previous_parent_id,
        )
        messages.success(request, "دسته‌بندی حذف شد.")
        return response


### NOTE:
# Deleting tags from staffpanel is intentionally disabled.


### NOTE:
# Deleting entities from staffpanel is intentionally disabled.


class PollListView(EditorialAdminRequiredMixin, ListView):
    model = Poll
    template_name = "staffpanel/poll_list.html"
    context_object_name = "polls"
    paginate_by = 20

    def get_queryset(self):
        now = timezone.now()
        queryset = (
            Poll.objects.all()
            .annotate(
                response_count=Count("responses", distinct=True),
                question_count=Count("questions", distinct=True),
            )
            .order_by("-created_at", "-id")
        )

        state_filter = (self.request.GET.get("state") or "all").strip().lower()
        query_text = (self.request.GET.get("q") or "").strip()

        if state_filter == "active":
            queryset = queryset.filter(is_active=True).filter(
                Q(starts_at__isnull=True) | Q(starts_at__lte=now)
            ).filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
        elif state_filter == "scheduled":
            queryset = queryset.filter(is_active=True, starts_at__gt=now)
        elif state_filter == "ended":
            queryset = queryset.filter(is_active=True, ends_at__lt=now)
        elif state_filter == "inactive":
            queryset = queryset.filter(is_active=False)

        if query_text:
            filters = Q(title__icontains=query_text)
            if query_text.isdigit():
                filters |= Q(id=int(query_text))
            queryset = queryset.filter(filters)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filters"] = {
            "state": (self.request.GET.get("state") or "all").strip().lower(),
            "q": (self.request.GET.get("q") or "").strip(),
        }
        context["now"] = timezone.now()
        context["state_options"] = [
            ("all", "همه"),
            ("active", "فعال"),
            ("scheduled", "زمان‌بندی‌شده"),
            ("ended", "پایان‌یافته"),
            ("inactive", "غیرفعال"),
        ]
        return context


class PollCreateView(EditorialAdminRequiredMixin, NextUrlMixin, CreateView):
    model = Poll
    form_class = PollStaffForm
    template_name = "staffpanel/poll_form.html"
    success_url_name = "staffpanel:poll-list"

    def form_valid(self, form):
        response = super().form_valid(form)
        _invalidate_active_poll_cache()
        messages.success(self.request, "نظرسنجی ایجاد شد.")
        return response

    def get_success_url(self):
        if "_continue" in self.request.POST:
            return reverse("staffpanel:poll-edit", kwargs={"pk": self.object.pk})
        return super().get_success_url()


class PollUpdateView(EditorialAdminRequiredMixin, NextUrlMixin, UpdateView):
    model = Poll
    form_class = PollStaffForm
    template_name = "staffpanel/poll_form.html"
    success_url_name = "staffpanel:poll-list"

    def form_valid(self, form):
        response = super().form_valid(form)
        _invalidate_active_poll_cache()
        messages.success(self.request, "نظرسنجی ویرایش شد.")
        return response

    def get_success_url(self):
        if "_continue" in self.request.POST:
            return reverse("staffpanel:poll-edit", kwargs={"pk": self.object.pk})
        return super().get_success_url()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["questions"] = self.object.questions.prefetch_related("choices").order_by("sort_order", "id")
        return context


class PollDeleteView(EditorialAdminRequiredMixin, NextUrlMixin, DeleteView):
    model = Poll
    template_name = "staffpanel/poll_confirm_delete.html"
    success_url_name = "staffpanel:poll-list"

    def post(self, request, *args, **kwargs):
        poll = self.get_object()
        if poll.responses.exists():
            messages.error(request, "نظرسنجی دارای پاسخ قابل حذف نیست.")
            return redirect(self.get_success_url())

        response = super().post(request, *args, **kwargs)
        _invalidate_active_poll_cache()
        messages.success(request, "نظرسنجی حذف شد.")
        return response


class PollStatsView(EditorialAdminRequiredMixin, DetailView):
    model = Poll
    template_name = "staffpanel/poll_stats.html"
    context_object_name = "poll"

    def get_queryset(self):
        return Poll.objects.prefetch_related("questions__choices")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        poll = self.object
        total_responses = poll.responses.count()
        total_answers = PollAnswer.objects.filter(response__poll=poll).count()

        choice_rows = (
            PollAnswer.objects.filter(response__poll=poll)
            .values("question_id", "choice_id")
            .annotate(total=Count("id"))
        )
        choice_map = {
            (row["question_id"], row["choice_id"]): int(row["total"])
            for row in choice_rows
        }

        response_rows = (
            PollAnswer.objects.filter(response__poll=poll)
            .values("question_id")
            .annotate(total=Count("response_id", distinct=True))
        )
        response_map = {row["question_id"]: int(row["total"]) for row in response_rows}

        question_stats = []
        for question in poll.questions.all():
            respondent_count = response_map.get(question.id, 0)
            choices = []
            for choice in question.choices.all():
                count = choice_map.get((question.id, choice.id), 0)
                ratio = round((count / respondent_count) * 100, 2) if respondent_count else 0.0
                choices.append(
                    {
                        "id": choice.id,
                        "text": choice.text,
                        "count": count,
                        "percent": ratio,
                    }
                )

            question_stats.append(
                {
                    "id": question.id,
                    "text": question.text,
                    "kind": question.kind,
                    "respondent_count": respondent_count,
                    "choices": choices,
                }
            )

        context.update(
            {
                "total_responses": total_responses,
                "total_answers": total_answers,
                "question_stats": question_stats,
            }
        )
        return context


class PollQuestionCreateView(EditorialAdminRequiredMixin, CreateView):
    model = PollQuestion
    form_class = PollQuestionStaffForm
    template_name = "staffpanel/poll_question_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.poll = get_object_or_404(Poll, pk=kwargs["poll_id"])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.poll = self.poll
        response = super().form_valid(form)
        _invalidate_active_poll_cache()
        messages.success(self.request, "سؤال ایجاد شد.")
        return response

    def get_success_url(self):
        return reverse("staffpanel:poll-edit", kwargs={"pk": self.poll.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["poll"] = self.poll
        return context


class PollQuestionUpdateView(EditorialAdminRequiredMixin, UpdateView):
    model = PollQuestion
    form_class = PollQuestionStaffForm
    template_name = "staffpanel/poll_question_form.html"
    context_object_name = "question"

    def form_valid(self, form):
        response = super().form_valid(form)
        _invalidate_active_poll_cache()
        messages.success(self.request, "سؤال ویرایش شد.")
        return response

    def get_success_url(self):
        return reverse("staffpanel:poll-edit", kwargs={"pk": self.object.poll_id})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["poll"] = self.object.poll
        return context


class PollQuestionDeleteView(EditorialAdminRequiredMixin, DeleteView):
    model = PollQuestion
    template_name = "staffpanel/poll_question_confirm_delete.html"
    context_object_name = "question"

    def post(self, request, *args, **kwargs):
        question = self.get_object()
        self._poll_id = question.poll_id
        if question.answers.exists():
            messages.error(request, "سؤال دارای پاسخ قابل حذف نیست.")
            return redirect(self.get_success_url())
        response = super().post(request, *args, **kwargs)
        _invalidate_active_poll_cache()
        messages.success(request, "سؤال حذف شد.")
        return response

    def get_success_url(self):
        poll_id = getattr(self, "_poll_id", None) or self.get_object().poll_id
        return reverse("staffpanel:poll-edit", kwargs={"pk": poll_id})


class PollChoiceCreateView(EditorialAdminRequiredMixin, CreateView):
    model = PollChoice
    form_class = PollChoiceStaffForm
    template_name = "staffpanel/poll_choice_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.question = get_object_or_404(PollQuestion, pk=kwargs["question_id"])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.question = self.question
        response = super().form_valid(form)
        _invalidate_active_poll_cache()
        messages.success(self.request, "گزینه ایجاد شد.")
        return response

    def get_success_url(self):
        return reverse("staffpanel:question-edit", kwargs={"pk": self.question.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["question"] = self.question
        context["poll"] = self.question.poll
        return context


class PollChoiceUpdateView(EditorialAdminRequiredMixin, UpdateView):
    model = PollChoice
    form_class = PollChoiceStaffForm
    template_name = "staffpanel/poll_choice_form.html"
    context_object_name = "choice"

    def form_valid(self, form):
        response = super().form_valid(form)
        _invalidate_active_poll_cache()
        messages.success(self.request, "گزینه ویرایش شد.")
        return response

    def get_success_url(self):
        return reverse("staffpanel:question-edit", kwargs={"pk": self.object.question_id})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["question"] = self.object.question
        context["poll"] = self.object.question.poll
        return context


class PollChoiceDeleteView(EditorialAdminRequiredMixin, DeleteView):
    model = PollChoice
    template_name = "staffpanel/poll_choice_confirm_delete.html"
    context_object_name = "choice"

    def post(self, request, *args, **kwargs):
        choice = self.get_object()
        self._question_id = choice.question_id
        if choice.answers.exists():
            messages.error(request, "گزینه دارای پاسخ قابل حذف نیست.")
            return redirect(self.get_success_url())
        response = super().post(request, *args, **kwargs)
        _invalidate_active_poll_cache()
        messages.success(request, "گزینه حذف شد.")
        return response

    def get_success_url(self):
        question_id = getattr(self, "_question_id", None) or self.get_object().question_id
        return reverse("staffpanel:question-edit", kwargs={"pk": question_id})


# ==========================
# Rankings (Staff CRUD)
# ==========================

RankingEntryFormSet = inlineformset_factory(
    RankingList,
    RankingEntry,
    form=RankingEntryStaffForm,
    extra=10,
    can_delete=True,
)


class RankingListView(EditorialAdminRequiredMixin, ListView):
    model = RankingList
    template_name = "staffpanel/ranking_list.html"
    context_object_name = "rankings"
    paginate_by = 20

    def get_queryset(self):
        qs = RankingList.objects.all().order_by("-updated_at", "-id")
        kind = (self.request.GET.get("kind") or "all").strip().lower()
        active = (self.request.GET.get("active") or "").strip()
        if kind in {"company", "model"}:
            qs = qs.filter(kind=kind)
        if active == "1":
            qs = qs.filter(is_active=True)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filters"] = {
            "kind": (self.request.GET.get("kind") or "all").strip().lower(),
            "active": (self.request.GET.get("active") or "").strip(),
        }
        context["kind_options"] = [
            ("all", "همه"),
            (RankingList.KIND_COMPANY, "شرکت"),
            (RankingList.KIND_MODEL, "مدل"),
        ]
        return context


class RankingCreateView(EditorialAdminRequiredMixin, TemplateView):
    template_name = "staffpanel/ranking_form.html"

    def get(self, request, *args, **kwargs):
        form = RankingListStaffForm()
        formset = RankingEntryFormSet()
        return self.render_to_response({"form": form, "formset": formset, "is_new": True})

    def post(self, request, *args, **kwargs):
        form = RankingListStaffForm(request.POST)
        if form.is_valid():
            ranking = form.save(commit=True)
            formset = RankingEntryFormSet(request.POST, instance=ranking)
            if formset.is_valid():
                formset.save()
                messages.success(request, "رتبه‌بندی با موفقیت ایجاد شد.")
                return redirect("staffpanel:ranking-list")
            ranking.delete()
        else:
            formset = RankingEntryFormSet(request.POST)
        return self.render_to_response({"form": form, "formset": formset, "is_new": True})


class RankingUpdateView(EditorialAdminRequiredMixin, TemplateView):
    template_name = "staffpanel/ranking_form.html"

    def get_object(self):
        return get_object_or_404(RankingList, pk=self.kwargs["pk"])

    def get(self, request, *args, **kwargs):
        ranking = self.get_object()
        form = RankingListStaffForm(instance=ranking)
        formset = RankingEntryFormSet(instance=ranking)
        return self.render_to_response({"form": form, "formset": formset, "ranking": ranking, "is_new": False})

    def post(self, request, *args, **kwargs):
        ranking = self.get_object()
        form = RankingListStaffForm(request.POST, instance=ranking)
        formset = RankingEntryFormSet(request.POST, instance=ranking)

        if form.is_valid() and formset.is_valid():
            form.save(commit=True)
            formset.save()
            messages.success(request, "رتبه‌بندی با موفقیت ویرایش شد.")
            return redirect("staffpanel:ranking-list")

        return self.render_to_response({"form": form, "formset": formset, "ranking": ranking, "is_new": False})


class RankingDeleteView(EditorialAdminRequiredMixin, DeleteView):
    model = RankingList
    template_name = "staffpanel/ranking_confirm_delete.html"
    success_url = reverse_lazy("staffpanel:ranking-list")

    def delete(self, request, *args, **kwargs):
        messages.success(request, "رتبه‌بندی با موفقیت حذف شد.")
        return super().delete(request, *args, **kwargs)


# ─────────────────────────────────────────────────────────────
# Editorial: Prompt Templates & Writing Rule Sets
# ─────────────────────────────────────────────────────────────


class PromptTemplateListView(ContentEditorRequiredMixin, ListView):
    model = PromptTemplate
    template_name = "staffpanel/prompt_list.html"
    context_object_name = "prompts"
    paginate_by = 20

    def get_queryset(self):
        qs = PromptTemplate.objects.all().order_by("-updated_at")

        status_filter = (self.request.GET.get("status") or "all").strip().lower()
        active_filter = (self.request.GET.get("active") or "").strip()
        query_text = (self.request.GET.get("q") or "").strip()

        if status_filter in {PromptTemplate.STATUS_DRAFT, PromptTemplate.STATUS_PUBLISHED, PromptTemplate.STATUS_ARCHIVED}:
            qs = qs.filter(status=status_filter)

        if active_filter in {"0", "1"}:
            qs = qs.filter(is_active=(active_filter == "1"))

        if query_text:
            qs = qs.filter(Q(title__icontains=query_text) | Q(key__icontains=query_text))

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            {
                "filters": {
                    "status": (self.request.GET.get("status") or "all").strip().lower(),
                    "active": (self.request.GET.get("active") or "").strip(),
                    "q": (self.request.GET.get("q") or "").strip(),
                },
                "status_options": [
                    ("all", "همه"),
                    (PromptTemplate.STATUS_PUBLISHED, "منتشر شده"),
                    (PromptTemplate.STATUS_DRAFT, "پیش‌نویس"),
                    (PromptTemplate.STATUS_ARCHIVED, "آرشیو"),
                ],
                "active_options": [
                    ("", "همه"),
                    ("1", "فعال"),
                    ("0", "غیرفعال"),
                ],
            }
        )
        return ctx


class PromptTemplateCreateView(EditorialAdminRequiredMixin, NextUrlMixin, CreateView):
    model = PromptTemplate
    form_class = PromptTemplateStaffForm
    template_name = "staffpanel/prompt_form.html"
    success_url_name = "staffpanel:prompt-list"

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.created_by = self.request.user
        obj.updated_by = self.request.user
        obj.save()
        self.object = obj
        messages.success(self.request, "پرامپت با موفقیت ایجاد شد.")
        return redirect(self.get_success_url())

    def get_success_url(self):
        if "_preview" in self.request.POST:
            return reverse("staffpanel:prompt-preview", kwargs={"pk": self.object.pk})
        if "_continue" in self.request.POST:
            return reverse("staffpanel:prompt-edit", kwargs={"pk": self.object.pk})
        return super().get_success_url()


class PromptTemplateUpdateView(EditorialAdminRequiredMixin, NextUrlMixin, UpdateView):
    model = PromptTemplate
    form_class = PromptTemplateStaffForm
    template_name = "staffpanel/prompt_form.html"
    success_url_name = "staffpanel:prompt-list"

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.updated_by = self.request.user
        obj.save()
        self.object = obj
        messages.success(self.request, "پرامپت با موفقیت ویرایش شد.")
        return redirect(self.get_success_url())

    def get_success_url(self):
        if "_preview" in self.request.POST:
            return reverse("staffpanel:prompt-preview", kwargs={"pk": self.object.pk})
        if "_continue" in self.request.POST:
            return reverse("staffpanel:prompt-edit", kwargs={"pk": self.object.pk})
        return super().get_success_url()


class PromptTemplatePreviewView(ContentEditorRequiredMixin, DetailView):
    model = PromptTemplate
    template_name = "staffpanel/prompt_preview.html"
    context_object_name = "prompt"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["rendered_body"] = render_markdown_safe(self.object.body)
        return ctx


class PromptTemplateDeleteView(EditorialAdminRequiredMixin, NextUrlMixin, DeleteView):
    model = PromptTemplate
    template_name = "staffpanel/editorial_confirm_delete.html"
    success_url_name = "staffpanel:prompt-list"

    def delete(self, request, *args, **kwargs):
        messages.success(request, "پرامپت با موفقیت حذف شد.")
        return super().delete(request, *args, **kwargs)


class WritingRuleSetListView(ContentEditorRequiredMixin, ListView):
    model = WritingRuleSet
    template_name = "staffpanel/ruleset_list.html"
    context_object_name = "rulesets"
    paginate_by = 20

    def get_queryset(self):
        qs = WritingRuleSet.objects.all().order_by("priority", "-updated_at")

        status_filter = (self.request.GET.get("status") or "all").strip().lower()
        active_filter = (self.request.GET.get("active") or "").strip()
        scenario_filter = (self.request.GET.get("scenario") or "").strip()
        query_text = (self.request.GET.get("q") or "").strip()

        if status_filter in {WritingRuleSet.STATUS_DRAFT, WritingRuleSet.STATUS_PUBLISHED, WritingRuleSet.STATUS_ARCHIVED}:
            qs = qs.filter(status=status_filter)

        if active_filter in {"0", "1"}:
            qs = qs.filter(is_active=(active_filter == "1"))

        if scenario_filter:
            qs = qs.filter(scenario__iexact=scenario_filter)

        if query_text:
            qs = qs.filter(Q(title__icontains=query_text) | Q(key__icontains=query_text) | Q(scenario__icontains=query_text))

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            {
                "filters": {
                    "status": (self.request.GET.get("status") or "all").strip().lower(),
                    "active": (self.request.GET.get("active") or "").strip(),
                    "scenario": (self.request.GET.get("scenario") or "").strip(),
                    "q": (self.request.GET.get("q") or "").strip(),
                },
                "status_options": [
                    ("all", "همه"),
                    (WritingRuleSet.STATUS_PUBLISHED, "منتشر شده"),
                    (WritingRuleSet.STATUS_DRAFT, "پیش‌نویس"),
                    (WritingRuleSet.STATUS_ARCHIVED, "آرشیو"),
                ],
                "active_options": [
                    ("", "همه"),
                    ("1", "فعال"),
                    ("0", "غیرفعال"),
                ],
            }
        )
        return ctx


class WritingRuleSetCreateView(EditorialAdminRequiredMixin, NextUrlMixin, CreateView):
    model = WritingRuleSet
    form_class = WritingRuleSetStaffForm
    template_name = "staffpanel/ruleset_form.html"
    success_url_name = "staffpanel:ruleset-list"

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.created_by = self.request.user
        obj.updated_by = self.request.user
        obj.save()
        form.save_m2m()
        self.object = obj
        messages.success(self.request, "قانون با موفقیت ایجاد شد.")
        return redirect(self.get_success_url())

    def get_success_url(self):
        if "_preview" in self.request.POST:
            return reverse("staffpanel:ruleset-preview", kwargs={"pk": self.object.pk})
        if "_continue" in self.request.POST:
            return reverse("staffpanel:ruleset-edit", kwargs={"pk": self.object.pk})
        return super().get_success_url()


class WritingRuleSetUpdateView(EditorialAdminRequiredMixin, NextUrlMixin, UpdateView):
    model = WritingRuleSet
    form_class = WritingRuleSetStaffForm
    template_name = "staffpanel/ruleset_form.html"
    success_url_name = "staffpanel:ruleset-list"

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.updated_by = self.request.user
        obj.save()
        form.save_m2m()
        self.object = obj
        messages.success(self.request, "قانون با موفقیت ویرایش شد.")
        return redirect(self.get_success_url())

    def get_success_url(self):
        if "_preview" in self.request.POST:
            return reverse("staffpanel:ruleset-preview", kwargs={"pk": self.object.pk})
        if "_continue" in self.request.POST:
            return reverse("staffpanel:ruleset-edit", kwargs={"pk": self.object.pk})
        return super().get_success_url()


class WritingRuleSetPreviewView(ContentEditorRequiredMixin, DetailView):
    model = WritingRuleSet
    template_name = "staffpanel/ruleset_preview.html"
    context_object_name = "ruleset"

    def get_queryset(self):
        return WritingRuleSet.objects.select_related("default_prompt").prefetch_related("prompts")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ruleset = self.object
        ctx["rendered_body"] = render_markdown_safe(ruleset.body)
        ctx["default_prompt"] = ruleset.default_prompt

        related_prompts = list(ruleset.prompts.all().order_by("title"))
        if ruleset.default_prompt:
            related_prompts = [p for p in related_prompts if p.pk != ruleset.default_prompt_id]
        ctx["related_prompts"] = related_prompts
        return ctx


class WritingRuleSetDeleteView(EditorialAdminRequiredMixin, NextUrlMixin, DeleteView):
    model = WritingRuleSet
    template_name = "staffpanel/editorial_confirm_delete.html"
    success_url_name = "staffpanel:ruleset-list"

    def delete(self, request, *args, **kwargs):
        messages.success(request, "قانون با موفقیت حذف شد.")
        return super().delete(request, *args, **kwargs)
