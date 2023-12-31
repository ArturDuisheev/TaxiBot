# Generated by Django 3.2 on 2022-05-16 12:48

from django.db import migrations
import phonenumber_field.modelfields


class Migration(migrations.Migration):

    dependencies = [
        ("cabinet", "0003_auto_20220514_1653"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="phone_number",
            field=phonenumber_field.modelfields.PhoneNumberField(
                blank=True,
                help_text="Может начинаться только с +7",
                max_length=128,
                null=True,
                region=None,
                verbose_name="Номер телефона",
            ),
        ),
    ]
