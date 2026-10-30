from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0008_orderitem_fulfilled_quantity_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="warehouse",
            name="assigned_staff",
            field=models.ManyToManyField(
                blank=True,
                related_name="assigned_warehouses",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
