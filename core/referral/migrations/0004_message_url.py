# Generated by Django 3.2 on 2022-08-06 10:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("referral", "0003_auto_20220514_1653"),
    ]

    operations = [
        migrations.AddField(
            model_name="message",
            name="url",
            field=models.URLField(
                blank=True, null=True, verbose_name="Ссылка в инлайн-кнопке"
            ),
        ),
    ]
