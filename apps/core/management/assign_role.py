
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError

from apps.core.permissions import (
    ADMIN_GROUP,
    WAREHOUSE_GROUP,
    SALES_GROUP,
)

# Use the custom user model configured in Django settings.
User = get_user_model()


class Command(BaseCommand):
    # Display the command's purpose in Django's management help.
    help = "Assign a role to an existing user"

    def add_arguments(self, parser):
        # Accept the username and one of the supported role names.
        parser.add_argument("username", type=str)
        parser.add_argument(
            "role",
            choices=[
                ADMIN_GROUP,
                WAREHOUSE_GROUP,
                SALES_GROUP,
            ],
        )

    def handle(self, *args, **options):
        # Find the existing account; never create users implicitly.
        try:
            user = User.objects.get(username=options["username"])
        except User.DoesNotExist:
            raise CommandError(
                f"User '{options['username']}' does not exist."
            )

        # Find the role group created by the create_roles command.
        try:
            group = Group.objects.get(name=options["role"])
        except Group.DoesNotExist:
            raise CommandError(
                "Role group not found. "
                "Run 'python manage.py create_roles' first."
            )

        # Add the selected role without removing existing group memberships.
        user.groups.add(group)

        # Confirm the assignment in the terminal.
        self.stdout.write(
            self.style.SUCCESS(
                f"Assigned '{group.name}' to '{user.username}'."
            )
        )
