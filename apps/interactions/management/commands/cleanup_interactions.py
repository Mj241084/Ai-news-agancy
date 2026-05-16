from __future__ import annotations
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.interactions.models import DailyArticleInteraction


class Command(BaseCommand):
    help = "Delete old DailyArticleInteraction records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep-days",
            type=int,
            default=90,
            help="Keep interaction rows for this many recent days.",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help="Backward-compatible alias for --keep-days",
        )

    def handle(self, *args, **options):
        keep_days = options["days"] if options["days"] is not None else options["keep_days"]
        cutoff = timezone.localdate() - timedelta(days=max(keep_days, 0))
        deleted_count, _ = DailyArticleInteraction.objects.filter(date__lt=cutoff).delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {deleted_count} interaction rows older than {cutoff} (keep_days={keep_days})"
            )
        )
