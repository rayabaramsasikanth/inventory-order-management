from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0010_orderstatushistory")]

    operations = [
        migrations.AddIndex(
            model_name="stockmovement",
            index=models.Index(fields=["warehouse", "-created_at"], name="movement_wh_created_idx"),
        ),
        migrations.AddIndex(
            model_name="stockmovement",
            index=models.Index(fields=["product", "-created_at"], name="movement_product_created_idx"),
        ),
        migrations.AddIndex(
            model_name="order",
            index=models.Index(fields=["warehouse", "status", "-created_at"], name="order_wh_status_created_idx"),
        ),
        migrations.AddIndex(
            model_name="order",
            index=models.Index(fields=["created_by", "-created_at"], name="order_creator_created_idx"),
        ),
    ]
