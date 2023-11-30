from crispy_forms.bootstrap import Div
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Fieldset, Layout, Submit, HTML
from django.contrib.gis import forms

from .models import User, Balance, Driver, TelegramData, Settings, Ban
from django.contrib.auth.models import Permission
from .settings import EXCLUDED_PERMISSION_FROM_ADMIN_FORM


class Card(Div):
    css_class = "card"


class CardHeader(Div):
    css_class = "card-header"

class CardDesk(Div):
    css_class = "card-desk"

class CardBody(Div):
    css_class = "card-body"


class CardFooter(Div):
    css_class = "card-footer text-end"


class LayoutMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        fields = self.base_fields
        header = self.layout_header if hasattr(self, "layout_header") else "Форма"
        desk = self.layout_desk if hasattr(self, "layout_desk") else ""
        buttons = (
            self.layout_buttons
            if hasattr(self, "layout_buttons")
            else [Submit("submit", "Сохранить", css_class="btn-primary")]
        )

        self.helper.layout = Layout(
            Card(
                CardHeader(HTML(f"<h5>{header}</h5>")),
                CardDesk(HTML(f'<p style="padding-inline: 40px">{desk}</p>')),
                CardBody(Fieldset(None, *fields)),
                CardFooter(
                    *buttons,
                ),
            )
        )


class UserForm(LayoutMixin, forms.ModelForm):
    """
    Форма для редактирования пользователя в кабинете администратора
    """

    helper = FormHelper()
    helper.form_method = "post"

    layout_header = "Основная информация о пользователе"
    layout_desk = "Рейтинг пользователя: "
    layout_buttons = [
        Submit("submit__user", "Сохранить", css_class="btn-primary"),
        Submit("delete__user", "Удалить", css_class="btn-secondary"),
        Submit("unban__user", "Снять все блокировки", css_class="btn-primary"),
    ]

    def __init__(self, *args, **kwargs):
        if kwargs.get("instance"):
            rating = kwargs["instance"].review_list__stars__avg if hasattr(kwargs["instance"], "review_list__stars__avg") else 0
            if rating is None:
                rating = "Не определен"
            
            self.layout_desk += str(rating)
        super().__init__(*args, **kwargs)
        self.fields["user_permissions"].queryset = Permission.objects.exclude(
            codename__in=EXCLUDED_PERMISSION_FROM_ADMIN_FORM
        )

    class Meta:
        model = User
        exclude = (
            "password",
            "location",
            "driver",
            "last_message_1_datetime",
            "groups",
            "is_active",
            "is_superuser",
        )


class BanUserForm(LayoutMixin, forms.ModelForm):

    helper = FormHelper()
    helper.form_method = "post"

    layout_header = "Блокировка пользователя"
    layout_buttons = [Submit("ban__user", "Заблокировать", css_class="btn-secondary")]

    class Meta:
        model = Ban
        exclude = ("user",)


class TelegramDataForm(LayoutMixin, forms.ModelForm):

    helper = FormHelper()
    helper.form_method = "POST"
    layout_header = "Информация из Телеграмма"
    layout_buttons = [
        Submit("submit__telegram_data", "Сохранить", css_class="btn-primary")
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["chat_id"].disabled = True

    class Meta:
        model = TelegramData
        fields = ("chat_id", "username", "photo")


class BalanceForm(LayoutMixin, forms.ModelForm):
    """
    Форма для редактирования баланса пользователя
    """

    helper = FormHelper()
    helper.form_method = "post"
    layout_header = "Баланс пользователя"
    layout_buttons = [Submit("submit__balance", "Сохранить", css_class="btn-primary")]

    class Meta:
        model = Balance
        fields = ("money", "bonuses", "free_days")


class DriverForm(LayoutMixin, forms.ModelForm):
    """
    Форма для редактирования данных водителя
    """

    car_brand = forms.CharField(max_length=255, label="Марка автомобиля")
    car_number = forms.CharField(max_length=20, label="Номер автомобиля")
    car_color = forms.CharField(max_length=50, label="Цвет автомобиля")

    helper = FormHelper()
    helper.form_method = "post"

    layout_header = "Водительские данные"
    layout_buttons = [
        Submit("submit__driver", "Сохранить", css_class="btn-primary"),
        Submit("delete__driver", "Забрать статус водителя", css_class="btn-secondary"),
    ]

    class Meta:
        model = Driver
        exclude = ("car",)


class SettingsForm(LayoutMixin, forms.ModelForm):

    helper = FormHelper()
    helper.form_method = "post"
    layout_header = "Настройки кабинета"
    layout_buttons = [Submit("submit__cabinet", "Сохранить", css_class="btn-primary")]

    class Meta:
        model = Settings
        fields = "__all__"
