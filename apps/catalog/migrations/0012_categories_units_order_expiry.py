from django.db import migrations, models
import django.db.models.deletion


def assign_legacy_product_defaults(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    ProductCategory = apps.get_model("catalog", "ProductCategory")
    UnitOfMeasure = apps.get_model("catalog", "UnitOfMeasure")
    db_alias = schema_editor.connection.alias

    category, _ = ProductCategory.objects.using(db_alias).get_or_create(
        slug="general", defaults={"name": "General"}
    )
    unit, _ = UnitOfMeasure.objects.using(db_alias).get_or_create(
        code="EA", defaults={"name": "Each", "decimal_places": 0}
    )
    Product.objects.using(db_alias).filter(category__isnull=True).update(category_id=category.pk)
    Product.objects.using(db_alias).filter(unit_of_measure__isnull=True).update(unit_of_measure_id=unit.pk)


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0011_query_performance_indexes"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True)),
                ("slug", models.SlugField(max_length=120, unique=True)),
                ("description", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["name"], "verbose_name_plural": "product categories"},
        ),
        migrations.CreateModel(
            name="UnitOfMeasure",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=20, unique=True)),
                ("name", models.CharField(max_length=80)),
                ("decimal_places", models.PositiveSmallIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.AddField(
            model_name="product",
            name="category",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="products", to="catalog.productcategory"),
        ),
        migrations.AddField(
            model_name="product",
            name="unit_of_measure",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="products", to="catalog.unitofmeasure"),
        ),
        migrations.RunPython(assign_legacy_product_defaults, migrations.RunPython.noop),
        migrations.AddField(
            model_name="order",
            name="expires_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]
