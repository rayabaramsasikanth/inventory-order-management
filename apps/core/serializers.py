
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
        extra_kwargs = {"email": {"required": True}}

        # The database generates the ID, so clients must not supply it.
        read_only_fields = ["id"]

    def validate_email(self, value):
        value = value.strip().lower()
        if not value:
            raise serializers.ValidationError("Email address is required.")
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def create(self, validated_data):
        # create_user() hashes the password before storing it.
        user = User.objects.create_user(**validated_data)
        user.email_verified = False
        user.save(update_fields=["email_verified"])
        return user

class HealthCheckSerializer(serializers.Serializer):
    status = serializers.CharField()
    service = serializers.CharField()


class RegisterResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField()
    message = serializers.CharField()


class LogoutRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class MessageResponseSerializer(serializers.Serializer):
    message = serializers.CharField()


class ProfileResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField()
    email_verified = serializers.BooleanField()

class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_new_password(self, value):
        user = self.context["request"].user
        validate_password(value, user=user)
        return value


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_new_password(self, value):
        validate_password(value)
        return value


class EmailVerificationSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()


class AccountDeactivationSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class EmailVerificationResendSerializer(serializers.Serializer):
    email = serializers.EmailField()
