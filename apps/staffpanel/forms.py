from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms import BaseInlineFormSet
from django.forms.models import inlineformset_factory

from apps.content.cache_invalidation import invalidate_article_cache, invalidate_listing_caches
from apps.content.models import Article, ArticleCategory, ArticleEntity, ArticleTag, ArticleSource, Source
from apps.entities.models import Entity, RankingEntry, RankingList
from apps.editorial.models import PromptTemplate, WritingRuleSet
from apps.interactions.models import Poll, PollChoice, PollQuestion
from apps.taxonomy.models import Category, Tag
from utils.slugs import unique_slugify


class ArticleStaffForm(forms.ModelForm):
    slug = forms.SlugField(required=False, allow_unicode=True)
    goals = forms.MultipleChoiceField(
        required=False,
        choices=[
            (Article.GOAL_VIEWS, "بازدید"),
            (Article.GOAL_COMMENTS, "کامنت"),
            (Article.GOAL_SHARES, "اشتراک‌گذاری"),
            (Article.GOAL_RATING, "امتیاز"),
        ],
        widget=forms.CheckboxSelectMultiple,
        label="هدف محتوا",
        help_text="(اختیاری) هدف/اهداف editorial برای این محتوا.",
    )
    tags = forms.ModelMultipleChoiceField(
        queryset=Tag.objects.filter(is_active=True).order_by("title"),
        required=False,
        label="تگ‌ها",
        widget=forms.SelectMultiple(attrs={"class": "js-filterable-select", "data-filter-name": "tags"}),
    )

    class Meta:
        model = Article
        fields = [
            "content_type",
            "title",
            "slug",
            "excerpt",
            "body",
            "hero_image",
            "thumbnail",
            "video_url",
            "video_thumbnail",
            "goals",
            "tags",
            "seo_title",
            "seo_description",
            "canonical_path",
            "meta_robots",
            "is_team_pick",
            "status",
        ]
        widgets = {
            "excerpt": forms.Textarea(attrs={"rows": 3}),
            "body": forms.Textarea(attrs={"rows": 18}),
            "hero_image": forms.URLInput(attrs={"placeholder": "https://example.com/images/hero-image.jpg"}),
            "thumbnail": forms.URLInput(attrs={"placeholder": "https://example.com/images/thumb.jpg"}),
            "video_url": forms.URLInput(attrs={"placeholder": "https://example.com/videos/news-clip.mp4"}),
            "video_thumbnail": forms.URLInput(attrs={"placeholder": "https://example.com/images/video-thumb.jpg"}),
            "seo_description": forms.Textarea(attrs={"rows": 3}),
            "canonical_path": forms.TextInput(attrs={"placeholder": "/p/my-news-article/"}),
            "meta_robots": forms.TextInput(attrs={"placeholder": "index,follow"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            # Slug is immutable (SEO)
            self.fields["slug"].disabled = True

            self.fields["tags"].initial = list(self.instance.article_tags.values_list("tag_id", flat=True))
            self.fields["goals"].initial = list(getattr(self.instance, "goals", []) or [])

        labels = {
            "content_type": "نوع محتوا",
            "title": "عنوان",
            "slug": "اسلاگ",
            "excerpt": "خلاصه",
            "body": "متن",
            "hero_image": "تصویر شاخص",
            "thumbnail": "تصویر تامنیل",
            "video_url": "لینک ویدیو",
            "video_thumbnail": "تصویر تامنیل ویدیو",
            "seo_title": "عنوان سئو",
            "seo_description": "توضیحات سئو",
            "canonical_path": "مسیر کنونیکال",
            "meta_robots": "دستور متا روبات",
            "is_team_pick": "پیشنهاد تیم",
            "status": "وضعیت",
        }
        for field_name, label in labels.items():
            if field_name in self.fields:
                self.fields[field_name].label = label

        help_texts = {
            "title": "عنوان اصلی که در صفحه و سئو نمایش داده می‌شود.",
            "slug": "اگر خالی بماند اتومات از عنوان ساخته می‌شود.",
            "excerpt": "خلاصه کوتاه برای لیست‌ها و متای توضیحات.",
            "body": "متن مارک‌دان.",
            "hero_image": "نشانی کامل تصویر هدر مقاله.",
            "thumbnail": "نشانی کامل تصویر کوچک برای کارت‌ها/لیست‌ها.",
            "video_url": "لینک ویدیو (اختیاری).",
            "video_thumbnail": "تصویر کاور ویدیو (اختیاری).",
            "seo_title": "اختیاری؛ اگر خالی باشد خودکار تولید می‌شود.",
            "seo_description": "اختیاری؛ اگر خالی باشد خودکار تولید می‌شود.",
            "canonical_path": "برای کنترل سئو در موارد خاص.",
            "meta_robots": "برای کنترل سئو در موارد خاص.",
            "status": "پیش‌نویس: فقط استاف می‌بیند / منتشر شده: عمومی.",
        }
        for field_name, text in help_texts.items():
            if field_name in self.fields:
                self.fields[field_name].help_text = text

        if "content_type" in self.fields:
            self.fields["content_type"].choices = [
                (Article.CONTENT_SHORT_NEWS, "خبر کوتاه"),
                (Article.CONTENT_POST, "پست"),
                (Article.CONTENT_ARTICLE, "مقاله"),
            ]
        if "status" in self.fields:
            self.fields["status"].choices = [
                (Article.STATUS_DRAFT, "پیش‌نویس"),
                (Article.STATUS_PUBLISHED, "منتشر شده"),
            ]

        if self.instance and self.instance.pk and "slug" in self.fields:
            self.fields["slug"].help_text = "اسلاگ بعد از ایجاد قابل تغییر نیست (برای حفظ صفحات ایندکس‌شده)."

    def clean_slug(self):
        if self.instance and self.instance.pk:
            return self.instance.slug
        return (self.cleaned_data.get("slug") or "").strip()

    @transaction.atomic
    def save(self, commit=True):
        article = super().save(commit=False)

        if not article.slug:
            unique_slugify(article, article.title, allow_unicode=True)

        # Normalize goals (remove empties, keep unique order)
        raw_goals = self.cleaned_data.get("goals") or []
        clean_goals = []
        seen = set()
        for g in raw_goals:
            g = str(g).strip()
            if not g or g in seen:
                continue
            seen.add(g)
            clean_goals.append(g)
        article.goals = clean_goals

        if commit:
            article.save()
            self._sync_tags(article)

        return article

    def _sync_tags(self, article: Article):
        selected_ids = set(self.cleaned_data.get("tags", Tag.objects.none()).values_list("id", flat=True))

        ArticleTag.objects.filter(article=article).exclude(tag_id__in=selected_ids).delete()

        existing_tag_ids = set(ArticleTag.objects.filter(article=article).values_list("tag_id", flat=True))
        for tag_id in selected_ids - existing_tag_ids:
            ArticleTag.objects.create(article=article, tag_id=tag_id)

class ArticleCategoryInlineForm(forms.ModelForm):
    class Meta:
        model = ArticleCategory
        fields = ["category", "is_primary", "weight"]
        widgets = {
            "category": forms.Select(attrs={"class": "js-filterable-select", "data-filter-name": "categories"}),
            "weight": forms.NumberInput(attrs={"step": "0.1", "min": "0.1", "max": "3.0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(is_active=True).order_by("order", "title")
        self.fields["is_primary"].label = "اصلی"
        self.fields["weight"].label = "وزن"
        self.fields["weight"].required = True
        self.fields["weight"].min_value = 0.1
        self.fields["weight"].max_value = 3.0


class BaseArticleCategoryFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        seen = set()
        primary_count = 0
        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            if form.cleaned_data.get("DELETE"):
                continue
            category = form.cleaned_data.get("category")
            if not category:
                continue
            if category.id in seen:
                raise ValidationError("یک دسته‌بندی تکراری در لیست دسته‌ها انتخاب شده است.")
            seen.add(category.id)
            if form.cleaned_data.get("is_primary"):
                primary_count += 1

        if primary_count > 1:
            raise ValidationError("فقط یک دسته‌بندی می‌تواند به عنوان دسته اصلی انتخاب شود.")


class ArticleSourceInlineForm(forms.ModelForm):
    class Meta:
        model = ArticleSource
        fields = ["source", "original_url", "note", "confidence"]
        widgets = {
            "source": forms.Select(attrs={"class": "js-filterable-select", "data-filter-name": "sources"}),
            "original_url": forms.URLInput(attrs={"placeholder": "https://..."}),
            "note": forms.TextInput(attrs={"placeholder": "یادداشت (اختیاری)"}),
            "confidence": forms.NumberInput(attrs={"step": "0.05", "min": "0", "max": "1"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["source"].queryset = Source.objects.filter(is_active=True).order_by("name")
        self.fields["source"].label = "منبع"
        self.fields["original_url"].label = "لینک اصلی"
        self.fields["note"].label = "یادداشت"
        self.fields["confidence"].label = "اعتماد"


class BaseArticleSourceFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        seen = set()
        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            if form.cleaned_data.get("DELETE"):
                continue
            source = form.cleaned_data.get("source")
            original_url = (form.cleaned_data.get("original_url") or "").strip()
            if not source and not original_url:
                continue
            if not source or not original_url:
                raise ValidationError("برای هر ردیف منبع، انتخاب منبع و لینک اصلی الزامی است.")
            key = (int(source.id), original_url)
            if key in seen:
                raise ValidationError("منبع تکراری با همان لینک اصلی اضافه شده است.")
            seen.add(key)




class ArticleEntityInlineForm(forms.ModelForm):
    class Meta:
        model = ArticleEntity
        fields = ["entity", "role", "importance"]
        widgets = {
            "entity": forms.Select(attrs={"class": "js-filterable-select", "data-filter-name": "entities"}),
            "role": forms.Select(),
            "importance": forms.NumberInput(attrs={"step": "0.1", "min": "0.1", "max": "3.0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["entity"].queryset = Entity.objects.filter(is_active=True).order_by("name")
        self.fields["entity"].label = "انتیتی"
        self.fields["role"].label = "نقش"
        self.fields["importance"].label = "اهمیت"

        self.fields["role"].choices = [
            (ArticleEntity.ROLE_MAIN, "اصلی"),
            (ArticleEntity.ROLE_MENTIONED, "اشاره‌شده"),
            (ArticleEntity.ROLE_AUTHOR, "نویسنده"),
            (ArticleEntity.ROLE_TARGET, "هدف/موضوع"),
        ]

        self.fields["importance"].required = True
        self.fields["importance"].min_value = 0.1
        self.fields["importance"].max_value = 3.0


class BaseArticleEntityFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        seen = set()
        main_count = 0
        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            if form.cleaned_data.get("DELETE"):
                continue
            entity = form.cleaned_data.get("entity")
            if not entity:
                continue
            role = form.cleaned_data.get("role") or ArticleEntity.ROLE_MENTIONED
            key = (int(entity.id), str(role))
            if key in seen:
                raise ValidationError("این انتیتی با همین نقش قبلاً اضافه شده است.")
            seen.add(key)
            if role == ArticleEntity.ROLE_MAIN:
                main_count += 1

        if main_count > 1:
            raise ValidationError("فقط یک انتیتی می‌تواند به عنوان انتیتی اصلی (Main) انتخاب شود.")


ArticleEntityFormSet = inlineformset_factory(
    Article,
    ArticleEntity,
    form=ArticleEntityInlineForm,
    formset=BaseArticleEntityFormSet,
    extra=0,
    can_delete=True,
)
ArticleCategoryFormSet = inlineformset_factory(
    Article,
    ArticleCategory,
    form=ArticleCategoryInlineForm,
    formset=BaseArticleCategoryFormSet,
    extra=0,
    can_delete=True,
)

ArticleSourceFormSet = inlineformset_factory(
    Article,
    ArticleSource,
    form=ArticleSourceInlineForm,
    formset=BaseArticleSourceFormSet,
    extra=0,
    can_delete=True,
)


class SourceStaffForm(forms.ModelForm):
    class Meta:
        model = Source
        fields = ["name", "url", "type", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        labels = {
            "name": "نام منبع",
            "url": "وب‌سایت",
            "type": "نوع",
            "is_active": "فعال",
        }
        for name, label in labels.items():
            if name in self.fields:
                self.fields[name].label = label
        self.fields["type"].choices = [
            (Source.TYPE_OFFICIAL, "رسمی"),
            (Source.TYPE_BLOG, "وبلاگ"),
            (Source.TYPE_PAPER, "مقاله علمی"),
            (Source.TYPE_SOCIAL, "شبکه اجتماعی"),
            (Source.TYPE_OTHER, "سایر"),
        ]



class CategoryStaffForm(forms.ModelForm):
    slug = forms.SlugField(required=False, allow_unicode=True)

    class Meta:
        model = Category
        fields = [
            "title",
            "slug",
            "parent",
            "description",
            "seo_title",
            "seo_description",
            "is_active",
            "is_indexable",
            "order",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "seo_description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        labels = {
            "title": "عنوان",
            "slug": "اسلاگ",
            "parent": "والد",
            "description": "توضیحات",
            "seo_title": "عنوان سئو",
            "seo_description": "توضیحات سئو",
            "is_active": "فعال",
            "is_indexable": "ایندکس‌پذیر",
            "order": "ترتیب نمایش",
        }
        for name, label in labels.items():
            if name in self.fields:
                self.fields[name].label = label

    def clean_parent(self):
        parent = self.cleaned_data.get("parent")
        if self.instance.pk and parent and parent.pk == self.instance.pk:
            raise forms.ValidationError("دسته‌بندی نمی‌تواند والد خودش باشد.")
        return parent

    def save(self, commit=True):
        obj = super().save(commit=False)
        if not obj.slug:
            unique_slugify(obj, obj.title, allow_unicode=True)
        if commit:
            obj.save()
        return obj


class TagStaffForm(forms.ModelForm):
    slug = forms.SlugField(required=False, allow_unicode=True)

    class Meta:
        model = Tag
        fields = [
            "title",
            "slug",
            "description",
            "seo_title",
            "seo_description",
            "is_active",
            "is_indexable",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "seo_description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        labels = {
            "title": "عنوان",
            "slug": "اسلاگ",
            "description": "توضیحات",
            "seo_title": "عنوان سئو",
            "seo_description": "توضیحات سئو",
            "is_active": "فعال",
            "is_indexable": "ایندکس‌پذیر",
        }
        for name, label in labels.items():
            if name in self.fields:
                self.fields[name].label = label

    def save(self, commit=True):
        obj = super().save(commit=False)
        if not obj.slug:
            unique_slugify(obj, obj.title, allow_unicode=True)
        if commit:
            obj.save()
        return obj


class EntityStaffForm(forms.ModelForm):
    slug = forms.SlugField(required=False, allow_unicode=True)
    aliases_text = forms.CharField(
        required=False,
        label="نام‌های جایگزین",
        help_text="نام‌های جایگزین را با ویرگول جدا کنید.",
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    class Meta:
        model = Entity
        fields = [
            "type",
            "name",
            "slug",
            "aliases_text",
            "description",
            "seo_title",
            "seo_description",
            "is_active",
            "is_indexable",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "seo_description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        aliases = []
        labels = {
            "type": "نوع",
            "name": "نام",
            "slug": "اسلاگ",
            "description": "توضیحات",
            "seo_title": "عنوان سئو",
            "seo_description": "توضیحات سئو",
            "is_active": "فعال",
            "is_indexable": "ایندکس‌پذیر",
        }
        for name, label in labels.items():
            if name in self.fields:
                self.fields[name].label = label

        if "type" in self.fields:
            self.fields["type"].choices = [
                (Entity.TYPE_COMPANY, "شرکت"),
                (Entity.TYPE_PERSON, "شخص"),
                (Entity.TYPE_MODEL, "مدل"),
                (Entity.TYPE_PRODUCT, "محصول"),
                (Entity.TYPE_LAB, "آزمایشگاه"),
                (Entity.TYPE_DATASET, "مجموعه‌داده"),
                (Entity.TYPE_OTHER, "سایر"),
            ]

        # Default: new entity pages are NOT indexable until explicitly enabled.
        if not (self.instance and self.instance.pk):
            self.fields["is_indexable"].initial = False
            self.fields["is_indexable"].help_text = "بدون اطمینان فعال نکنید!!!"

        if self.instance and self.instance.pk and isinstance(self.instance.aliases, list):
            aliases = self.instance.aliases
        self.fields["aliases_text"].initial = ", ".join(str(item).strip() for item in aliases if str(item).strip())

    def clean_aliases_text(self):
        raw_value = self.cleaned_data.get("aliases_text") or ""
        parts = [part.strip() for part in raw_value.replace("\n", ",").split(",")]
        return [part for part in parts if part]

    def save(self, commit=True):
        obj = super().save(commit=False)
        if not obj.slug:
            unique_slugify(obj, obj.name, allow_unicode=True)
        obj.aliases = self.cleaned_data.get("aliases_text", [])
        if commit:
            obj.save()
        return obj



class PromptTemplateStaffForm(forms.ModelForm):
    key = forms.SlugField(required=False, allow_unicode=True)

    class Meta:
        model = PromptTemplate
        fields = [
            "title",
            "key",
            "description",
            "body",
            "language",
            "status",
            "is_active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "body": forms.Textarea(attrs={"rows": 16}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        labels = {
            "title": "عنوان",
            "key": "کلید",
            "description": "توضیح کوتاه",
            "body": "متن پرامپت",
            "language": "زبان",
            "status": "وضعیت",
            "is_active": "فعال",
        }
        for name, label in labels.items():
            if name in self.fields:
                self.fields[name].label = label

        help_texts = {
            "key": "اگر خالی باشد از عنوان ساخته می‌شود (پیشنهاد: یک کلید پایدار انتخاب کنید).",
            "body": "این متن می‌تواند مارک‌دان باشد و بلوک کد هم داشته باشد.",
        }
        for name, ht in help_texts.items():
            if name in self.fields:
                self.fields[name].help_text = ht

        if "status" in self.fields:
            self.fields["status"].choices = [
                (PromptTemplate.STATUS_PUBLISHED, "منتشر شده"),
                (PromptTemplate.STATUS_DRAFT, "پیش‌نویس"),
                (PromptTemplate.STATUS_ARCHIVED, "آرشیو"),
            ]

    def save(self, commit=True):
        obj = super().save(commit=False)
        if not obj.key:
            unique_slugify(obj, obj.title, allow_unicode=True)
        if commit:
            obj.save()
        return obj


class WritingRuleSetStaffForm(forms.ModelForm):
    key = forms.SlugField(required=False, allow_unicode=True)
    applies_to_content_types = forms.MultipleChoiceField(
        required=False,
        choices=[
            (Article.CONTENT_SHORT_NEWS, "خبر کوتاه"),
            (Article.CONTENT_POST, "پست"),
            (Article.CONTENT_ARTICLE, "مقاله"),
        ],
        label="محدود به نوع محتوا",
        help_text="اگر خالی باشد یعنی برای همه نوع محتوا قابل استفاده است.",
        widget=forms.SelectMultiple,
    )
    categories = forms.ModelMultipleChoiceField(
        queryset=Category.objects.filter(is_active=True).order_by("order", "title"),
        required=False,
        label="دسته‌ها",
    )
    tags = forms.ModelMultipleChoiceField(
        queryset=Tag.objects.filter(is_active=True).order_by("title"),
        required=False,
        label="تگ‌ها",
    )
    prompts = forms.ModelMultipleChoiceField(
        queryset=PromptTemplate.objects.filter(is_active=True).order_by("title"),
        required=False,
        label="پرامپت‌های مرتبط",
    )

    class Meta:
        model = WritingRuleSet
        fields = [
            "title",
            "key",
            "description",
            "scenario",
            "applies_to_content_types",
            "categories",
            "tags",
            "default_prompt",
            "prompts",
            "priority",
            "body",
            "status",
            "is_active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "body": forms.Textarea(attrs={"rows": 18}),
            "scenario": forms.TextInput(attrs={"placeholder": "مثلاً: آموزشی، تحلیل، راهنما..."}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        labels = {
            "title": "عنوان",
            "key": "کلید",
            "description": "توضیح کوتاه",
            "scenario": "سناریو",
            "default_prompt": "پرامپت پیشنهادی",
            "priority": "اولویت",
            "body": "قوانین/راهنما",
            "status": "وضعیت",
            "is_active": "فعال",
        }
        for name, label in labels.items():
            if name in self.fields:
                self.fields[name].label = label

        # Improve default prompt queryset for UX
        if "default_prompt" in self.fields:
            self.fields["default_prompt"].queryset = PromptTemplate.objects.filter(is_active=True).order_by("title")
            self.fields["default_prompt"].required = False

        if "status" in self.fields:
            self.fields["status"].choices = [
                (WritingRuleSet.STATUS_PUBLISHED, "منتشر شده"),
                (WritingRuleSet.STATUS_DRAFT, "پیش‌نویس"),
                (WritingRuleSet.STATUS_ARCHIVED, "آرشیو"),
            ]

        # Ensure initial is list for MultipleChoiceField (JSONField)
        if self.instance and self.instance.pk:
            self.fields["applies_to_content_types"].initial = list(self.instance.applies_to_content_types or [])

    def save(self, commit=True):
        obj = super().save(commit=False)
        if not obj.key:
            unique_slugify(obj, obj.title, allow_unicode=True)

        if commit:
            obj.save()
            self.save_m2m()
        return obj



class PollStaffForm(forms.ModelForm):
    class Meta:
        model = Poll
        fields = [
            "title",
            "is_active",
            "starts_at",
            "ends_at",
        ]
        widgets = {
            "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["starts_at"].required = False
        self.fields["ends_at"].required = False
        self.fields["starts_at"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"]
        self.fields["ends_at"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"]
        self.fields["title"].label = "عنوان"
        self.fields["is_active"].label = "فعال"
        self.fields["starts_at"].label = "شروع"
        self.fields["ends_at"].label = "پایان"
        self.fields["starts_at"].help_text = "اختیاری؛ اگر خالی باشد نظرسنجی از همین حالا شروع می‌شود."
        self.fields["ends_at"].help_text = "اختیاری؛ اگر خالی باشد زمان پایان ندارد."

    def clean(self):
        cleaned = super().clean()
        starts_at = cleaned.get("starts_at")
        ends_at = cleaned.get("ends_at")
        if starts_at and ends_at and ends_at <= starts_at:
            raise forms.ValidationError("زمان پایان باید بعد از زمان شروع باشد.")
        return cleaned


class PollQuestionStaffForm(forms.ModelForm):
    class Meta:
        model = PollQuestion
        fields = [
            "text",
            "kind",
            "sort_order",
        ]
        widgets = {
            "text": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["text"].label = "متن سؤال"
        self.fields["kind"].label = "نوع"
        self.fields["sort_order"].label = "ترتیب"
        self.fields["kind"].choices = [
            (PollQuestion.KIND_SINGLE, "تک‌گزینه‌ای"),
            (PollQuestion.KIND_MULTI, "چندگزینه‌ای"),
        ]


class PollChoiceStaffForm(forms.ModelForm):
    class Meta:
        model = PollChoice
        fields = [
            "text",
            "sort_order",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["text"].label = "متن گزینه"
        self.fields["sort_order"].label = "ترتیب"


import json


class RankingListStaffForm(forms.ModelForm):
    columns_text = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 6,
                "placeholder": "کلید|برچسب\nname|نام\nscore|امتیاز\nurl|لینک\n",
            }
        ),
        help_text="هر خط یک ستون: کلید|برچسب. اگر خالی باشد، ستون پویایی ثبت نمی‌شود.",
        label="ستون‌ها",
    )

    class Meta:
        model = RankingList
        fields = ["title", "kind", "is_active"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "مثلاً: رتبه‌بندی مدل‌های این هفته"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].label = "عنوان"
        self.fields["kind"].label = "نوع"
        self.fields["is_active"].label = "فعال"

        if self.instance and self.instance.pk:
            raw = self.instance.columns if isinstance(self.instance.columns, list) else []
            lines = []
            for col in raw:
                if not isinstance(col, dict):
                    continue
                key = str(col.get("key") or "").strip()
                if not key:
                    continue
                label = str(col.get("label") or key).strip() or key
                lines.append(f"{key}|{label}")
            self.fields["columns_text"].initial = "\n".join(lines)

    def clean_columns_text(self):
        text = (self.cleaned_data.get("columns_text") or "").strip()
        if not text:
            return []

        columns = []
        seen = set()
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "|" in line:
                key, label = line.split("|", 1)
            elif ":" in line:
                key, label = line.split(":", 1)
            else:
                key, label = line, line
            key = key.strip()
            label = label.strip() or key
            if not key:
                continue
            if key in seen:
                raise forms.ValidationError(f"کلید تکراری: {key}")
            seen.add(key)
            columns.append({"key": key, "label": label})

        return columns

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.columns = self.cleaned_data.get("columns_text") or []
        if commit:
            obj.save()
        return obj


class RankingEntryStaffForm(forms.ModelForm):
    data_json = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "{\"metric\": 0.95}"}),
        help_text="JSON اختیاری برای داده‌های اضافی (در صورت نیاز).",
        label="داده اضافه (JSON)",
    )

    class Meta:
        model = RankingEntry
        fields = ["rank", "name", "score"]
        widgets = {
            "rank": forms.NumberInput(attrs={"min": 1}),
            "name": forms.TextInput(attrs={"placeholder": "نام آیتم"}),
            "score": forms.NumberInput(attrs={"step": "any"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["rank"].label = "رتبه"
        self.fields["name"].label = "نام"
        self.fields["score"].label = "امتیاز"

        if self.instance and self.instance.pk:
            try:
                self.fields["data_json"].initial = json.dumps(self.instance.data or {}, ensure_ascii=False, indent=2)
            except Exception:
                self.fields["data_json"].initial = ""

    def clean_data_json(self):
        raw = (self.cleaned_data.get("data_json") or "").strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            raise forms.ValidationError("فرمت JSON نامعتبر است.")
        if not isinstance(parsed, dict):
            raise forms.ValidationError("داده اضافه باید یک شیء JSON باشد.")
        return parsed

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.data = self.cleaned_data.get("data_json") or {}
        if commit:
            obj.save()
        return obj
