from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import mark_safe

from . import models


# Register your models here.


class BansInlineAdmin(admin.TabularInline):
    model = models.Ban
    extra = 0


class UserTabularInline(admin.TabularInline):
    model = models.User
    extra = 0


class CustomUserAdmin(UserAdmin):

    list_display = (
        "photo_as_view",
        "username",
        "email",
        "first_name",
        "last_name",
        "is_staff",
    )

    fieldsets = UserAdmin.fieldsets + (
        (
            "Кастомная админка",
            {"fields": ("driver", "coupons", "used_coupons", "location")},
        ),
    )

    inlines = UserAdmin.inlines + [BansInlineAdmin]

    def photo_as_view(self, obj: models.User):
        return mark_safe(
            '<img style="%s" src ="%s" width="50" height="50"/>'
            % ("border-radius: 50%", obj.get_photo_url())
        )


admin.site.register(models.User, CustomUserAdmin)
admin.site.register(models.Driver)
admin.site.register(models.TelegramData)
admin.site.register(models.Balance)
admin.site.register(models.Ban)
admin.site.register(models.Settings)
