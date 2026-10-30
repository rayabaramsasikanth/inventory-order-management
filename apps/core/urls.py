
from django.urls import path

# Use SimpleJWT's tested views instead of implementing token generation ourselves.
from rest_framework_simplejwt.views import (
    TokenRefreshView,
)

# Import our API class-based views.
from .views import (
    HealthCheckView,
    RegisterView,
    LogoutView,
    ProfileView,
    LoginView,
    PasswordChangeView,
    PasswordResetRequestView,
    PasswordResetConfirmView, EmailVerificationView, EmailVerificationResendView, AccountDeactivationView,
)


urlpatterns = [
    # Public endpoint used by health checks and monitoring.
    path("health/", HealthCheckView.as_view(), name="health-check"),

    # Public endpoint for creating a new account.
    path("auth/register/", RegisterView.as_view(), name="register"),

    # Validate username and password, then issue access and refresh tokens.
    path(
        "auth/login/",
        LoginView.as_view(),
        name="token_obtain_pair",
    ),

    # Exchange a valid refresh token for a new access token.
    path(
        "auth/token/refresh/",
        TokenRefreshView.as_view(),
        name="token_refresh",
    ),

    # Revoke the supplied refresh token.
    path("auth/logout/", LogoutView.as_view(), name="logout"),

    # Return the authenticated user's profile.
    path("auth/profile/", ProfileView.as_view(), name="profile"),
    path("auth/password/change/", PasswordChangeView.as_view(), name="password-change"),
    path("auth/password/reset/", PasswordResetRequestView.as_view(), name="password-reset"),
    path("auth/password/reset/confirm/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
    path("auth/verify-email/", EmailVerificationView.as_view(), name="verify-email"),
    path("auth/verify-email/resend/", EmailVerificationResendView.as_view(), name="verify-email-resend"),
    path("auth/deactivate/", AccountDeactivationView.as_view(), name="account-deactivate"),
]
