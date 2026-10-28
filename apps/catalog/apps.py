
from django.apps import AppConfig


class CatalogConfig(AppConfig):
    # Use BigAutoField for automatically generated primary keys.
    default_auto_field = "django.db.models.BigAutoField"

    # Full Python path of this Django app.
    name = "apps.catalog"

    # Short label used by Django for this app.
    label = "catalog"
