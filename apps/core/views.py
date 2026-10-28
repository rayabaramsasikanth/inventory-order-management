
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import RegisterSerializer


class HealthCheckView(APIView):
    # Monitoring tools must be able to check the API without logging in.
    permission_classes = [AllowAny]

    def get(self, request):
        # Return a simple response to confirm that the API is running.
        return Response({
            "status": "healthy",
            "service": "inventory-order-management",
        })


class RegisterView(APIView):
    # New users must be able to register before they have an account.
    permission_classes = [AllowAny]

    def post(self, request):
        # Validate the incoming registration data using the serializer.
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # The serializer creates the user and hashes the password.
        user = serializer.save()

        # Never return the user's password in the API response.
        return Response(
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "message": "Registration successful",
            },
            status=status.HTTP_201_CREATED,
        )


class LogoutView(APIView):
    # Only an authenticated user can request logout.
    permission_classes = [IsAuthenticated]

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
            token.blacklist()
        except TokenError:
            # Return a client error for invalid or already-revoked tokens.
            raise ValidationError({
                "refresh": "Invalid or revoked refresh token."
            })

        return Response({"message": "Logout successful"})


class ProfileView(APIView):
    # A valid JWT access token is required to view this profile.
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # DRF sets request.user after successful authentication.
        user = request.user

        # Return only the account details the client needs.
        return Response({
            "id": user.id,
            "username": user.username,
            "email": user.email,
        })
