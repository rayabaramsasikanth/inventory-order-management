
import os
import logging
import binascii

from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework.exceptions import AuthenticationFailed
from .throttles import (
    LoginRateThrottle, RegistrationRateThrottle, PasswordResetRateThrottle,
)

from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model, authenticate
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.conf import settings

from .serializers import (
    HealthCheckSerializer, LogoutRequestSerializer, MessageResponseSerializer,
    ProfileResponseSerializer, RegisterResponseSerializer, RegisterSerializer,
    PasswordChangeSerializer, PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer, EmailVerificationSerializer,
    AccountDeactivationSerializer, EmailVerificationResendSerializer,
)

from drf_spectacular.utils import extend_schema

logger = logging.getLogger("apps.auth")


class HealthCheckView(APIView):
    # Monitoring tools must be able to check the API without logging in.
    permission_classes = [AllowAny]

    @extend_schema(
        responses={200: HealthCheckSerializer}
    )
    def get(self, request):
        # Return a simple response to confirm that the API is running.
        return Response({
            "status": "healthy",
            "service": "inventory-order-management",
        })


class RegisterView(APIView):
    throttle_classes = [RegistrationRateThrottle]
    # New users must be able to register before they have an account.
    permission_classes = [AllowAny]

    @extend_schema(
        request=RegisterSerializer,
        responses={201: RegisterResponseSerializer},
    )
    def post(self, request):
        # Validate the incoming registration data using the serializer.
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # The serializer creates the user with email_verified=False.
        user = serializer.save()
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        verification_url = os.getenv(
            "FRONTEND_EMAIL_VERIFICATION_URL",
            "http://localhost:3000/verify-email",
        )
        verification_link = f"{verification_url}?uid={uid}&token={token}"
        try:
            send_mail(
                "Verify your Inventory API account",
                f"Verify your email using this link: {verification_link}",
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False,
            )
        except Exception:
            logger.exception("Email verification delivery failed user_id=%s", user.pk)

        # Never return the user's password or verification token in the API response.
        return Response(
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "message": "Registration successful. Check your email for the verification link.",
            },
            status=status.HTTP_201_CREATED,
        )


class AuditedTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        request = self.context.get("request")
        try:
            # Check verification before SimpleJWT creates an outstanding token.
            candidate = authenticate(
                request=request,
                username=attrs.get("username"),
                password=attrs.get("password"),
            )
            if candidate is not None and not getattr(candidate, "email_verified", True):
                raise AuthenticationFailed("Verify your email before signing in.")
            data = super().validate(attrs)
        except AuthenticationFailed:
            ip_address = request.META.get("REMOTE_ADDR", "unknown") if request else "unknown"
            logger.warning("Authentication failed from ip=%s", ip_address)
            raise
        logger.info("Authentication succeeded user_id=%s", self.user.pk)
        return data


class LoginView(TokenObtainPairView):
    throttle_classes = [LoginRateThrottle]
    serializer_class = AuditedTokenObtainPairSerializer


class EmailVerificationView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    @extend_schema(request=EmailVerificationSerializer, responses=MessageResponseSerializer)
    def post(self, request):
        serializer = EmailVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            uid = force_str(urlsafe_base64_decode(serializer.validated_data["uid"]))
            user = get_user_model().objects.get(pk=uid, is_active=True)
        except (ValueError, TypeError, OverflowError, binascii.Error, get_user_model().DoesNotExist):
            raise ValidationError({"token": "Invalid or expired verification link."})
        if user.email_verified:
            return Response({"message": "Email address is already verified."})
        if not default_token_generator.check_token(user, serializer.validated_data["token"]):
            raise ValidationError({"token": "Invalid or expired verification link."})
        user.email_verified = True
        user.save(update_fields=["email_verified"])
        logger.info("Email verified user_id=%s", user.pk)
        return Response({"message": "Email address verified successfully. You can now sign in."})


class EmailVerificationResendView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    @extend_schema(request=EmailVerificationResendSerializer, responses=MessageResponseSerializer)
    def post(self, request):
        serializer = EmailVerificationResendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        user = get_user_model().objects.filter(
            email__iexact=email, is_active=True, email_verified=False
        ).first()
        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            verification_url = os.getenv(
                "FRONTEND_EMAIL_VERIFICATION_URL",
                "http://localhost:3000/verify-email",
            )
            link = f"{verification_url}?uid={uid}&token={token}"
            try:
                send_mail(
                    "Verify your Inventory API account",
                    f"Verify your email using this link: {link}",
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                    fail_silently=False,
                )
            except Exception:
                logger.exception("Verification resend failed user_id=%s", user.pk)
        return Response({"message": "If the account requires verification, instructions have been sent."})


class AccountDeactivationView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=AccountDeactivationSerializer, responses=MessageResponseSerializer)
    def post(self, request):
        serializer = AccountDeactivationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not request.user.check_password(serializer.validated_data["password"]):
            raise ValidationError({"password": "Password is incorrect."})
        user = request.user
        user.is_active = False
        user.save(update_fields=["is_active"])
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
        for outstanding in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=outstanding)
        logger.info("Account deactivated user_id=%s", user.pk)
        return Response({"message": "Account deactivated successfully."})


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=PasswordChangeSerializer, responses=MessageResponseSerializer)
    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        if not request.user.check_password(serializer.validated_data["old_password"]):
            raise ValidationError({"old_password": "Current password is incorrect."})
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
        for outstanding in OutstandingToken.objects.filter(user=request.user):
            BlacklistedToken.objects.get_or_create(token=outstanding)
        return Response({"message": "Password changed successfully. Please log in again."})


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    @extend_schema(request=PasswordResetRequestSerializer, responses=MessageResponseSerializer)
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        User = get_user_model()
        # Always return the same response so callers cannot enumerate accounts.
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_url = os.getenv("FRONTEND_PASSWORD_RESET_URL", "http://localhost:3000/reset-password")
            link = f"{reset_url}?uid={uid}&token={token}"
            try:
                send_mail(
                    "Password reset request",
                    f"Use this link to reset your password: {link}",
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                    fail_silently=False,
                )
            except Exception:
                # Do not reveal account existence through mail delivery errors.
                logger.exception("Password reset email delivery failed")
        return Response({"message": "If an account matches that email, password reset instructions have been sent."})


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    @extend_schema(request=PasswordResetConfirmSerializer, responses=MessageResponseSerializer)
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            uid = force_str(urlsafe_base64_decode(serializer.validated_data["uid"]))
            user = get_user_model().objects.get(pk=uid, is_active=True)
        except (ValueError, TypeError, OverflowError, binascii.Error, get_user_model().DoesNotExist):
            raise ValidationError({"token": "Invalid or expired reset token."})
        if not default_token_generator.check_token(user, serializer.validated_data["token"]):
            raise ValidationError({"token": "Invalid or expired reset token."})
        from django.contrib.auth.password_validation import validate_password
        validate_password(serializer.validated_data["new_password"], user=user)
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
        for outstanding in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=outstanding)
        return Response({"message": "Password reset successfully. Please log in again."})


class LogoutView(APIView):
    # Only an authenticated user can request logout.
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=LogoutRequestSerializer,
        responses={200: MessageResponseSerializer},
    )
    def post(self, request):
        # The client sends the refresh token it wants to revoke.
        refresh_token = request.data.get("refresh")

        # Reject the request if the refresh token is missing.
        if not refresh_token:
            raise ValidationError({
                "refresh": "Refresh token is required."
            })

        try:
            # Validate the token and add it to the blacklist.
            # A blacklisted refresh token cannot be used again.
            token = RefreshToken(refresh_token)
            if str(token.get("user_id")) != str(request.user.pk):
                raise ValidationError({"refresh": "This refresh token does not belong to the authenticated user."})
            token.blacklist()
        except TokenError:
            raise ValidationError({"refresh": "Invalid or revoked refresh token."})

        return Response({"message": "Logout successful"})


class ProfileView(APIView):
    # A valid JWT access token is required to view this profile.
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=ProfileResponseSerializer)
    def get(self, request):
        # DRF sets request.user after successful authentication.
        user = request.user

        # Return only the account details the client needs.
        return Response({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "email_verified": user.email_verified,
        })
