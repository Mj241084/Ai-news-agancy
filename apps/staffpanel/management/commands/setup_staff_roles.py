from __future__ import annotations

from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group

from apps.staffpanel.mixins import GROUP_CONTENT_EDITORS, GROUP_EDITORIAL_ADMINS


class Command(BaseCommand):
    help = "Create default staff groups used by the custom staffpanel RBAC."

    def handle(self, *args, **options):
        created = []
        for name in (GROUP_CONTENT_EDITORS, GROUP_EDITORIAL_ADMINS):
            group, was_created = Group.objects.get_or_create(name=name)
            if was_created:
                created.append(name)

        if created:
            self.stdout.write(self.style.SUCCESS(f"Created groups: {', '.join(created)}"))
        else:
            self.stdout.write(self.style.SUCCESS("Groups already exist."))

        self.stdout.write(
            "\nNext steps:\n"
            f"- Assign staff users who should create/edit articles/tags/entities to group '{GROUP_CONTENT_EDITORS}'.\n"
            f"- Assign staff users who should manage everything (including categories and prompts/rules CRUD) to group '{GROUP_EDITORIAL_ADMINS}'.\n"
        )
