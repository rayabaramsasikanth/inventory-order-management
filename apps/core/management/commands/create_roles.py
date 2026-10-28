
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group

from apps.core.permissions import (
    ADMIN_GROUP,
    WAREHOUSE_GROUP,
    SALES_GROUP,
)


class Command(BaseCommand):
    # Display this description when someone runs python manage.py help.
    help = "Create the standard user groups for the inventory system"

    def handle(self, *args, **options):
        # Keep role names in one place so they match our permission classes.
        role_names = [
            ADMIN_GROUP,
            WAREHOUSE_GROUP,
            SALES_GROUP,
        ]

        for role_name in role_names:
            # Create the group only if it does not already exist.
            # Running this command repeatedly is therefore safe.
            group, created = Group.objects.get_or_create(
                name=role_name
            )

            if created:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created role: {role_name}"
                    )
                )
            else:
                self.stdout.write(
                    f"Role already exists: {role_name}"
                )
