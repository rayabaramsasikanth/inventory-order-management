
from django.urls import path

# Use SimpleJWT's tested views instead of implementing token generation ourselves.
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

# Import our API class-based views.
from .views import (
    HealthCheckView,
    RegisterView,
    LogoutView,
    ProfileView,
)


urlpatterns = [
    # Public endpoint used by health checks and monitoring.
    path("health/", HealthCheckView.as_view(), name="health-check"),

    # Public endpoint for creating a new account.
    path("auth/register/", RegisterView.as_view(), name="register"),

    # Validate username and password, then issue access and refresh tokens.
    path(
        "auth/login/",
        TokenObtainPairView.as_view(),
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
]
