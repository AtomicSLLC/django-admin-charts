# Generated by Django 3.2.8 on 2021-12-09 07:22

from django.conf import settings
from django.db import migrations, models


try:
    if getattr(settings, "ADMIN_CHARTS_USE_JSONFIELD", True):
        from django.db.models import JSONField
    else:
        from jsonfield.fields import JSONField
except ImportError:
    from jsonfield.fields import JSONField


class Migration(migrations.Migration):

    dependencies = [
        ("admin_tools_stats", "0014_auto_20211122_1511"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="cachedvalue",
            options={"ordering": ("order",)},
        ),
        migrations.AddField(
            model_name="cachedvalue",
            name="order",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="cachedvalue",
            name="dynamic_choices",
            field=JSONField(default=dict),
        ),
    ]
