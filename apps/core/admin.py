from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import IdempotencyRecord, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Account verification", {"fields": ("email_verified",)}),)
    list_display = UserAdmin.list_display + ("email_verified",)


@admin.register(IdempotencyRecord)
class IdempotencyRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "key", "state", "response_status", "created_at", "expires_at")
    list_filter = ("state", "created_at")
    search_fields = ("user__username", "key")
    readonly_fields = ("user", "key", "request_hash", "state", "response_status", "response_body", "created_at", "expires_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
