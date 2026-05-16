from __future__ import annotations

import json

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Prefetch, Q
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.interactions.models import Poll, PollAnswer, PollChoice, PollQuestion, PollResponse
from apps.interactions.services import get_or_create_visitor_from_request
from utils.caching import make_cache_key


ACTIVE_POLL_CACHE_KEY = make_cache_key("polls:active:html")


def _json_response(payload: dict, *, status: int = 200):
    response = JsonResponse(payload, status=status)
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


def _parse_body(request) -> dict:
    if request.content_type and "application/json" in request.content_type:
        try:
            return json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return {}
    return request.POST.dict()


def _active_poll_queryset():
    now = timezone.now()
    return (
        Poll.objects.filter(is_active=True)
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
    )


def _normalize_answers(raw_answers) -> dict[int, list[int]]:
    if not isinstance(raw_answers, dict):
        return {}

    result: dict[int, list[int]] = {}
    for raw_question_id, raw_choice_ids in raw_answers.items():
        try:
            question_id = int(raw_question_id)
        except (TypeError, ValueError):
            continue

        values = raw_choice_ids
        if not isinstance(values, list):
            values = [values]

        cleaned = []
        for raw_choice_id in values:
            try:
                cleaned.append(int(raw_choice_id))
            except (TypeError, ValueError):
                continue

        deduped = list(dict.fromkeys(cleaned))
        result[question_id] = deduped

    return result


@require_GET
def ajax_active_poll_view(request):
    cached_html = cache.get(ACTIVE_POLL_CACHE_KEY)
    if cached_html is not None:
        if cached_html:
            return _json_response({"has_poll": True, "html": cached_html})
        return _json_response({"has_poll": False})

    poll = (
        _active_poll_queryset()
        .order_by("-created_at", "-id")
        .prefetch_related(
            Prefetch(
                "questions",
                queryset=PollQuestion.objects.order_by("sort_order", "id").prefetch_related(
                    Prefetch("choices", queryset=PollChoice.objects.order_by("sort_order", "id"))
                ),
            )
        )
        .first()
    )

    if not poll:
        cache.set(ACTIVE_POLL_CACHE_KEY, "", timeout=60)
        return _json_response({"has_poll": False})

    html = render_to_string("partials/_poll_form.html", {"poll": poll}, request=request)
    cache.set(ACTIVE_POLL_CACHE_KEY, html, timeout=60)
    return _json_response({"has_poll": True, "html": html})


@require_POST
def ajax_submit_poll_view(request):
    payload = _parse_body(request)

    try:
        poll_id = int(payload.get("poll_id"))
    except (TypeError, ValueError):
        return _json_response({"ok": False, "message": "نظرسنجی نامعتبر است."}, status=400)

    raw_answers = payload.get("answers")
    if isinstance(raw_answers, str):
        try:
            raw_answers = json.loads(raw_answers)
        except json.JSONDecodeError:
            raw_answers = {}
    answers = _normalize_answers(raw_answers)

    poll = (
        _active_poll_queryset()
        .filter(pk=poll_id)
        .prefetch_related(
            Prefetch(
                "questions",
                queryset=PollQuestion.objects.order_by("sort_order", "id").prefetch_related(
                    Prefetch("choices", queryset=PollChoice.objects.order_by("sort_order", "id"))
                ),
            )
        )
        .first()
    )
    if not poll:
        return _json_response({"ok": False, "message": "نظرسنجی فعال نیست."}, status=400)

    questions = list(poll.questions.all())
    question_ids = {question.id for question in questions}
    if not question_ids:
        return _json_response({"ok": False, "message": "این نظرسنجی سوالی ندارد."}, status=400)

    if set(answers.keys()) - question_ids:
        return _json_response({"ok": False, "message": "پاسخ نامعتبر ارسال شده است."}, status=400)

    normalized_answers: dict[int, list[int]] = {}
    for question in questions:
        selected_ids = answers.get(question.id, [])
        if not selected_ids:
            return _json_response({"ok": False, "message": "پاسخ همه سوال‌ها الزامی است."}, status=400)

        valid_choice_ids = {choice.id for choice in question.choices.all()}
        if not set(selected_ids).issubset(valid_choice_ids):
            return _json_response({"ok": False, "message": "گزینه نامعتبر ارسال شده است."}, status=400)

        if question.kind == PollQuestion.KIND_SINGLE and len(selected_ids) != 1:
            return _json_response({"ok": False, "message": "برای سوال تک‌انتخابی فقط یک گزینه مجاز است."}, status=400)
        if question.kind == PollQuestion.KIND_MULTI and len(selected_ids) < 1:
            return _json_response({"ok": False, "message": "برای سوال چندانتخابی حداقل یک گزینه لازم است."}, status=400)

        normalized_answers[question.id] = selected_ids

    actor_kwargs = {}
    if request.user.is_authenticated:
        actor_kwargs["user"] = request.user
    else:
        actor_kwargs["visitor"] = getattr(request, "visitor", None) or get_or_create_visitor_from_request(request)

    try:
        with transaction.atomic():
            response = PollResponse.objects.create(poll=poll, **actor_kwargs)
            question_map = {question.id: question for question in questions}

            for question_id, selected_ids in normalized_answers.items():
                question = question_map[question_id]
                for choice_id in selected_ids:
                    PollAnswer.objects.create(
                        response=response,
                        question=question,
                        choice_id=choice_id,
                    )
    except IntegrityError:
        return _json_response({"ok": False, "message": "قبلاً ثبت شده"}, status=409)

    return _json_response({"ok": True, "message": "ثبت شد ✅"})
