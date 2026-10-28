
# Get the user model configured in Django settings.
# This supports our custom User model instead of hardcoding a model class.
from django.contrib.auth import get_user_model

# Apply Django's configured password-strength validation rules.
from django.contrib.auth.password_validation import validate_password

# ModelSerializer converts model data to and from API-friendly representations.
from rest_framework import serializers


# Retrieve the active user model configured by AUTH_USER_MODEL.
User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    # Accept the password during registration, but never include it
    # in serialized API output.
    # Django's password validators check whether it is sufficiently strong.
    password = serializers.CharField(
        write_only=True,
        validators=[validate_password],
    )

    class Meta:
        # Tell DRF which model this serializer creates.
        model = User

        # Only expose these fields through the registration API.
        fields = ["id", "username", "email", "password"]

        # The database generates the ID, so clients must not supply it.
        read_only_fields = ["id"]

    def create(self, validated_data):
        # create_user() hashes the password before storing it.
        # Never use User.objects.create() with a raw password here.
        return User.objects.create_user(**validated_data)
