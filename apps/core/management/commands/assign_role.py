from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError

from apps.core.permissions import (
    ADMIN_GROUP,
    WAREHOUSE_GROUP,
    SALES_GROUP,
)

User = get_user_model()


class Command(BaseCommand):
    # Describe the purpose of this management command.
    help = "Assign a role to an existing user"

    def add_arguments(self, parser):
        # Accept the username and one supported role.
        parser.add_argument("username", type=str)
        parser.add_argument(
            "role",
            choices=[ADMIN_GROUP, WAREHOUSE_GROUP, SALES_GROUP],
        )

    def handle(self, *args, **options):
        # Find the existing user; do not create accounts automatically.
        try:
            user = User.objects.get(username=options["username"])
        except User.DoesNotExist:
            raise CommandError(
                f"User '{options['username']}' does not exist."
            )

        # Find the role group created by create_roles.
        try:
            group = Group.objects.get(name=options["role"])
        except Group.DoesNotExist:
            raise CommandError(
                "Role group not found. Run 'python manage.py create_roles' first."
            )

        # Add the role without removing the user's existing group memberships.
        user.groups.add(group)

        self.stdout.write(
            self.style.SUCCESS(
                f"Assigned '{group.name}' to '{user.username}'."
            )
        )
