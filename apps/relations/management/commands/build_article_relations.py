from __future__ import annotations
from django.core.management.base import BaseCommand, CommandError

from apps.relations import services


class Command(BaseCommand):
    help = "Build weighted article relations graph."

    def add_arguments(self, parser):
        parser.add_argument(
            "--article",
            type=str,
            default=None,
            help="Article id or slug to build relations for a single article.",
        )
        parser.add_argument(
            "--article-id",
            type=int,
            default=None,
            help="Backward-compatible alias for --article",
        )
        parser.add_argument("--top-n", type=int, default=None)
        parser.add_argument("--max-candidates", type=int, default=None)
        parser.add_argument("--horizon-days", type=int, default=None)
        parser.add_argument("--algo-version", type=str, default=None)
        parser.add_argument("--recent-days", type=int, default=30)
        parser.add_argument("--days", type=int, default=None, help="Backward-compatible alias for --recent-days")

    def handle(self, *args, **options):
        article_identifier = options["article"] or options["article_id"]
        recent_days = options["days"] if options["days"] is not None else options["recent_days"]

        kwargs = {
            "top_n": options["top_n"],
            "max_candidates": options["max_candidates"],
            "horizon_days": options["horizon_days"],
            "algo_version": options["algo_version"],
        }

        filtered_kwargs = {key: value for key, value in kwargs.items() if value is not None}

        if article_identifier:
            try:
                rows = services.build_relations_for_article(article_identifier, **filtered_kwargs)
            except Exception as exc:
                raise CommandError(f"Failed to build relations for article={article_identifier}: {exc}") from exc
            self.stdout.write(
                self.style.SUCCESS(
                    f"Built {len(rows)} relation rows for article={article_identifier}"
                )
            )
            return

        rebuilt = services.rebuild_relations_for_recent(
            days=recent_days,
            **filtered_kwargs,
        )
        self.stdout.write(self.style.SUCCESS(f"Rebuilt relations for {rebuilt} recent articles."))
