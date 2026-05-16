from __future__ import annotations
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.personalization.services import ensure_daily_interest_cached, ensure_daily_recs_cached


class Command(BaseCommand):
    help = "Warm daily personalization cache for recent users."

    def add_arguments(self, parser):
        parser.add_argument("--users", type=int, default=20, help="How many recent users to warm.")
        parser.add_argument("--algo-version", type=str, default=None)

    def handle(self, *args, **options):
        limit = options["users"]
        algo_version = options["algo_version"]
        today = timezone.localdate()
        user_model = get_user_model()
        users = user_model.objects.order_by("-date_joined")[:limit]

        warmed = 0
        for user in users:
            ensure_daily_interest_cached(user, date=today, algo_version=algo_version)
            ensure_daily_recs_cached(user, date=today, algo_version=algo_version)
            warmed += 1

        self.stdout.write(self.style.SUCCESS(f"Warm-up completed for {warmed} users."))
