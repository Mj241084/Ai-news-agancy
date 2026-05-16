from __future__ import annotations
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.interactions.models import Poll, PollAnswer, PollChoice, PollQuestion, PollResponse


class PollAjaxTests(TestCase):
    def setUp(self):
        cache.clear()
        now = timezone.now()
        self.poll = Poll.objects.create(
            title="Test Poll",
            is_active=True,
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=1),
        )
        self.question_single = PollQuestion.objects.create(
            poll=self.poll,
            text="Single question",
            kind=PollQuestion.KIND_SINGLE,
            sort_order=1,
        )
        self.question_multi = PollQuestion.objects.create(
            poll=self.poll,
            text="Multi question",
            kind=PollQuestion.KIND_MULTI,
            sort_order=2,
        )
        self.single_choice_1 = PollChoice.objects.create(question=self.question_single, text="A", sort_order=1)
        self.single_choice_2 = PollChoice.objects.create(question=self.question_single, text="B", sort_order=2)
        self.multi_choice_1 = PollChoice.objects.create(question=self.question_multi, text="X", sort_order=1)
        self.multi_choice_2 = PollChoice.objects.create(question=self.question_multi, text="Y", sort_order=2)

        self.active_url = reverse("interactions:ajax_active_poll")
        self.submit_url = reverse("interactions:ajax_submit_poll")

    def _post_json(self, url: str, payload: dict):
        return self.client.post(url, data=json.dumps(payload), content_type="application/json")

    def test_active_endpoint_returns_html_when_poll_exists(self):
        response = self.client.get(self.active_url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["has_poll"])
        self.assertIn("<form", data["html"])
        self.assertIn("Single question", data["html"])

    def test_active_endpoint_returns_false_when_no_poll(self):
        self.poll.is_active = False
        self.poll.save(update_fields=["is_active"])
        cache.clear()

        response = self.client.get(self.active_url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["has_poll"])

    def test_guest_submit_creates_response_then_returns_409_on_duplicate(self):
        payload = {
            "poll_id": self.poll.id,
            "answers": {
                str(self.question_single.id): [self.single_choice_1.id],
                str(self.question_multi.id): [self.multi_choice_1.id, self.multi_choice_2.id],
            },
        }

        first = self._post_json(self.submit_url, payload)
        self.assertEqual(first.status_code, 200)
        first_data = first.json()
        self.assertTrue(first_data["ok"])
        self.assertEqual(first_data["message"], "ثبت شد ✅")
        self.assertEqual(PollResponse.objects.count(), 1)
        self.assertEqual(PollAnswer.objects.count(), 3)

        second = self._post_json(self.submit_url, payload)
        self.assertEqual(second.status_code, 409)
        second_data = second.json()
        self.assertFalse(second_data["ok"])
        self.assertEqual(second_data["message"], "قبلاً ثبت شده")
        self.assertEqual(PollResponse.objects.count(), 1)

    def test_submit_validates_required_answers(self):
        payload = {
            "poll_id": self.poll.id,
            "answers": {
                str(self.question_single.id): [self.single_choice_1.id],
            },
        }
        response = self._post_json(self.submit_url, payload)
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["ok"])

    def test_authenticated_user_can_submit_once(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(
            username="poll-user",
            email="poll@example.com",
            password="secret12345",
        )
        self.client.force_login(user)

        payload = {
            "poll_id": self.poll.id,
            "answers": {
                str(self.question_single.id): [self.single_choice_2.id],
                str(self.question_multi.id): [self.multi_choice_2.id],
            },
        }

        first = self._post_json(self.submit_url, payload)
        second = self._post_json(self.submit_url, payload)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(PollResponse.objects.filter(user=user, poll=self.poll).count(), 1)
