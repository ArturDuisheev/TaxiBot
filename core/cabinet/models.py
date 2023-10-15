import binascii
import datetime
import os

from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import Group as BaseGroup
from django.contrib.gis.db import models
from django.urls import reverse
from django.utils import timezone
from phonenumber_field.modelfields import PhoneNumberField
from rest_framework.authtoken.models import Token

from dispatcher.settings import BAD_ORDER_STARS
from referral.models import Coupon, Message
from . import utils
from .fields import BonusesField, MoneyField
from .managers import (
    BanQuerySet,
    CustomUserManager,
    UserQuerySet,
    WorkDriverDayQuerySet,
)
from .settings import DRIVER_PHOTO_UPLOAD_TO


class Group(BaseGroup):
    class Meta:
        verbose_name = "Должность"
        verbose_name_plural = "Должности"


class UserManager(CustomUserManager.from_queryset(UserQuerySet)):
    use_in_migrations = True


class User(AbstractUser):
    """
    Модель юзера, главная в системе. Связана с Balance,  Ban, BanHistory, Coupon
    """

    coupons = models.ManyToManyField(
        Coupon, blank=True, verbose_name="Промокоды", related_name="users"
    )
    used_coupons = models.ManyToManyField(
        Coupon,
        blank=True,
        verbose_name="Использованные промокоды",
        related_name="used_users",
    )
    driver = models.OneToOneField(
        "cabinet.Driver", blank=True, null=True, on_delete=models.SET_NULL
    )
    location = models.OneToOneField(
        "dispatcher.Location",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name="Местоположение пользователя",
        related_name="user",
    )
    mentor = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="Ментор (пригласивший)",
        related_name="heirs",
    )
    phone_number = PhoneNumberField(
        verbose_name="Номер телефона",
        help_text="Может начинаться только с +7",
        null=True,
        blank=True,
    )

    last_message_1_datetime = models.DateTimeField(
        default=timezone.now,
        verbose_name="Дата последней отправки сообщения о том, что 5 дней не было заказов",
    )

    objects = UserManager()

    def __str__(self):
        return self.username

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
        ordering = ["-pk"]

    def get_absolute_url(self):
        return reverse("cabinet:user", args=[self.pk])

    def create_api_token(self) -> Token:
        """
        Создает и привязывает токен для API аутентификации к пользователю. Возвращает созданный токен.
        """
        token = Token.objects.create(user=self)
        token.save()
        return token

    def get_photo_url(self) -> str:
        if hasattr(self, "telegram_data"):
            if self.telegram_data.photo:
                return self.telegram_data.photo.url
        else:
            return "/static/media/avatar.png"

    @property
    def status_name(self) -> str:
        # Возвращает статус пользователя, как строку
        if self.is_staff:
            return "Администратор"
        if self.driver:
            return "Водитель"
        else:
            return "Клиент"

    @property
    def can_create_order(self) -> bool:
        return not bool(self.orders.in_progress())

    def update_balance(self, value):
        from cabinet.utils.balance import update_user_balance

        # Обновляет баланс пользователя

        update_user_balance(user_id=self.pk, value=value)

    def get_bad_orders(self):
        # Возвращает заказы, на которые пользователь поставил низкую оценку
        return self.orders.filter(review__stars__lte=BAD_ORDER_STARS)

    @property
    def is_blocked(self):
        # Возвращает значение True or False. True - пользователь заблокирован в данный момент
        return bool(self.bans.active())

    def ban(
        self,
        end_date: datetime.datetime,
        start_date: datetime.datetime = timezone.now(),
    ):
        """
        Функция для блокировки пользователя
        """
        ban = Ban(user=self, start_date=start_date, end_date=end_date)
        ban.save()
        return ban

    def ban_for_days(self, days: int):
        """
        Блокирует пользователя на определенное количество дней
        """
        time_now = timezone.now()
        delta = datetime.timedelta(days=days)
        self.ban(end_date=time_now + delta, start_date=time_now)

    def unban(self):
        self.bans.active().update(end_date=timezone.now())


class TelegramAuthToken(models.Model):
    """
    The default authorization token model.
    """

    key = models.CharField("Токен", max_length=40, primary_key=True)
    user = models.OneToOneField(
        User,
        related_name="telegram_auth_token",
        on_delete=models.CASCADE,
        verbose_name="Пользователь",
    )
    created = models.DateTimeField("Дата создания", auto_now_add=True)

    class Meta:
        verbose_name = "Токен для авторизации через Telegram"
        verbose_name_plural = "Токены для авторизации через Telegram"

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = self.generate_key()
        return super().save(*args, **kwargs)

    @classmethod
    def generate_key(cls):
        return binascii.hexlify(os.urandom(20)).decode()

    def __str__(self):
        return self.key


class TelegramData(models.Model):
    """
    Модель, хранящая данные о пользователя из Телеграмма. Связана с моделью пользователя
    Primary Key - chat_id
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        verbose_name="Пользователь",
        related_name="telegram_data",
    )
    chat_id = models.BigIntegerField(
        primary_key=True, verbose_name="ID пользователя в Telegram"
    )
    username = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Юзернейм пользователя в Telegram",
    )
    registration_date = models.DateTimeField(
        auto_now_add=True, verbose_name="Дата регистрации в чат-боте"
    )
    photo = models.ImageField(
        upload_to=utils.get_telegram_data_upload_path,
        default="../static/media/avatar.png",
        verbose_name="Фото профиля в Telegram",
    )

    def __str__(self):
        return "%s -> %s" % (self.chat_id, self.user)

    class Meta:
        verbose_name = "Телеграммные данные"
        verbose_name_plural = verbose_name


class Balance(models.Model):
    """
    Хранит количество денег,бонусов и историю транзакций привязывается к модели пользователя. Уникален для каждого пользователя.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="balance",
        verbose_name="Пользователь",
    )
    money = MoneyField(default=0)
    bonuses = BonusesField(default=0)
    free_days = models.PositiveSmallIntegerField(default=0, verbose_name="Бонусные дни")

    def __str__(self):
        return (
            f"Balance of %s | {self.money=} {self.bonuses=} {self.free_days=}"
            % self.user.username
        )

    class Meta:
        verbose_name = "Баланс"
        verbose_name_plural = "Балансы"


class AbstractBan(models.Model):
    """
    Абстрактная Модель для блокировки пользователя. Указывается дата выдачи блокировки и дата окончания.
    """

    start_date = models.DateTimeField(
        default=timezone.now, verbose_name="Дата блокировки"
    )
    end_date = models.DateTimeField(verbose_name="Дата разблокировки")

    class Meta:
        abstract = True
        verbose_name = "Блокировка"
        verbose_name_plural = "Блокировки"
        ordering = ("-start_date",)

    def is_active(self):
        return self.start_date < timezone.now() < self.end_date


class Ban(AbstractBan):
    """
    История блокировок пользователя.
    """

    user = models.ForeignKey(
        "cabinet.User", on_delete=models.CASCADE, related_name="bans"
    )

    objects = BanQuerySet.as_manager()

    def __str__(self):
        return "%s | %s -> %s" % (
            self.user,
            self.start_date.date(),
            self.end_date.date(),
        )


# Driver models
class Driver(models.Model):
    """
    Модель для данных водителей, связана с моделью пользователя
    """

    car = models.OneToOneField(
        "cabinet.Car",
        on_delete=models.CASCADE,
        related_name="driver",
        verbose_name="Автомобиль",
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Дата регистрации как водителя"
    )
    baby_chair = models.BooleanField(
        default=False, verbose_name="Есть ли детское кресло"
    )
    phone_number = PhoneNumberField(
        verbose_name="Номер телефона водителя", help_text="Может начинаться только с +7"
    )
    photo = models.ImageField(
        upload_to=DRIVER_PHOTO_UPLOAD_TO, verbose_name="Фотография водителя", blank=True, null=True
    )
    time_blocked_message_order = models.DateTimeField(null=True, blank=True)
    
    count_not_accepted = models.IntegerField(null=True, blank=True, default=0)

    @property
    def is_active(self):
        # Возвращает True, если водитель в данный момент на линии (идёт рабочий день)
        return bool(self.work_days.active())



class Car(models.Model):
    brand = models.ForeignKey(
        "cabinet.CarBrand", verbose_name="Марка автомобиля", on_delete=models.PROTECT
    )
    number = models.CharField(
        max_length=6, verbose_name="Номер автомобиля", help_text="Например: А766НН"
    )
    color = models.CharField(max_length=50, verbose_name="Цвет автомобиля")


class CarBrand(models.Model):
    """
    Модель марки автомобиля, чтобы избежать многочисленных повторений и в будущем добавить систему классов: эконом, бизнес и тд.
    """

    name = models.CharField(max_length=150, verbose_name="Марка автомобиля")

    def __str__(self):
        return self.name


class WorkDriverDay(models.Model):
    """
    Рабочие дни водителя
    """

    start_date = models.DateTimeField(verbose_name="Дата начала рабочего дня")
    end_date = models.DateTimeField(verbose_name="Дата окончания рабочего дня")
    driver = models.ForeignKey(
        Driver,
        on_delete=models.CASCADE,
        verbose_name="Данные водителя",
        related_name="work_days",
    )

    objects = WorkDriverDayQuerySet.as_manager()

    def is_active(self):
        return self.start_date < timezone.now() < self.end_date


class Settings(models.Model):
    """
    Настройки кабинета
    """

    # Стоимость выхода на линию
    out_line_cost = MoneyField(verbose_name="Стоимость выхода на линию")
    mentor_coupon = models.ForeignKey(
        Coupon,
        on_delete=models.PROTECT,
        verbose_name="Купон, который выдается ментору за приглашение",
        related_name="mentor_coupons",
    )
    mentor_coupon_2 = models.ForeignKey(
        Coupon,
        on_delete=models.PROTECT,
        verbose_name="Купон, который выдается ментору, если водитель вышел на линию 7 раз.",
        related_name="mentor_coupons_2",
    )
    hirer_coupon = models.ForeignKey(
        Coupon,
        on_delete=models.PROTECT,
        verbose_name="Купон, который выдается приглашенному при " "регистрации",
        related_name="hirer_coupons",
    )

    message_1 = models.ForeignKey(
        Message,
        on_delete=models.PROTECT,
        verbose_name="Сообщение, которое отправляется пользователям, которые 5 дней не делали заказ",
        related_name="messages_1",
    )
    message_2 = models.ForeignKey(
        Message,
        on_delete=models.PROTECT,
        verbose_name="Сообщение, которое отправляется водителям, когда кончаются бесплатные дни",
        related_name="messages_2",
    )
    hide_cabinet_button = models.BooleanField(
        "Скрыть кнопку личного кабинета", default=False
    )

    class Meta:
        verbose_name = "Настройки кабинета"
        verbose_name_plural = verbose_name


class SettingsDriverMessageBan(models.Model):

    count_not_accepted = models.PositiveIntegerField(verbose_name="Количество отказов")

    count_minute_blocked = models.PositiveIntegerField(verbose_name="Колличество минут блокировки")

    class Meta:
        verbose_name = "Настройки блокировки водителя"
        verbose_name_plural = verbose_name