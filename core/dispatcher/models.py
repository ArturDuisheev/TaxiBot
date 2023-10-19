from decimal import Decimal

from cabinet.fields import MoneyField
from cabinet.settings import PAYMENT_METHODS
from django.conf.global_settings import TIME_ZONE
from django.contrib.auth import get_user_model
from django.contrib.gis.db import models
from django.urls import reverse
from phonenumber_field.modelfields import PhoneNumberField
from referral.models import Coupon
from timezone_field import TimeZoneField

from .managers import (
    CityQuerySet,
    LocationQuerySet,
    OrderQuerySet,
    get_point_by_lat_lon,
)
from .settings import (
    DEFAULT_BABY_CHAIR_COST,
    MINIMAL_COST_OF_RIDE,
    ORDER_IS_CREATED,
    ORDER_STATUSES,
    STARS_TYPES,
    SEARCH_NEAREST_DRIVERS_RADIUS,
)
from django.contrib.gis.geos import Point


# Получаем модель пользователя
User = get_user_model()


class Order(models.Model):
    """
    Модель заказа поездки, связана с клиентом, водителем и отзывом
    """

    client = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="orders", verbose_name="Клиент"
    )
    driver = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="rides",
        verbose_name="Водитель",
    )
    start_location = models.OneToOneField(
        "dispatcher.Location",
        on_delete=models.PROTECT,
        related_name="order_start_location",
    )
    end_location = models.OneToOneField(
        "dispatcher.Location",
        on_delete=models.PROTECT,
        related_name="order_end_location",
    )
    raw_cost = MoneyField(verbose_name="Стоимость заказа без применения купонов")
    cost = MoneyField(verbose_name="Стоимость заказа")
    address = models.ForeignKey(
        "dispatcher.Address", on_delete=models.PROTECT, verbose_name="Адрес"
    )
    finish_address = models.ForeignKey(
        "dispatcher.Address",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        verbose_name="Адрес точки прибытия",
        related_name="finish_addresses",
    )
    payment_method = models.CharField(
        max_length=20, choices=PAYMENT_METHODS, verbose_name="Вид оплаты"
    )
    client_phone = PhoneNumberField(
        verbose_name="Номер телефона клиента", help_text="Может начинаться только с +7"
    )
    status = models.PositiveSmallIntegerField(
        choices=ORDER_STATUSES,
        default=ORDER_IS_CREATED,
        db_index=True,
        verbose_name="Статус заказа",
    )

    coupon = models.ForeignKey(
        Coupon,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        verbose_name="Примененный купон",
    )
    suitable_drivers = models.ManyToManyField(
        User, verbose_name="Найденные подходящие водители"
    )
    is_need_baby_chair = models.BooleanField(
        default=False, verbose_name="Нужно ли детское кресло"
    )
    comment = models.TextField(
        max_length=1000, blank=True, null=True, verbose_name="Комментарий к заказу"
    )
    start_driver_location = models.ForeignKey(
        "dispatcher.Location",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        verbose_name="Геопозиция водителя при принятии заказа",
        related_name="order_start_driver_location",
    )
    pull_up_driver_location = models.ForeignKey(
        "dispatcher.Location",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        verbose_name="Геопозиция водителя при ожидании клиента",
        related_name="order_pull_up_driver_location",
    )
    review = models.OneToOneField(
        "dispatcher.OrderReview",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        verbose_name="Отзыв",
        related_name="order",
    )

    # Даты и время
    start_date = models.DateTimeField(
        auto_now_add=True, verbose_name="Дата получения заказа"
    )
    take_order_date = models.DateTimeField(
        blank=True, null=True, verbose_name="Дата принятия заказа"
    )
    driver_pull_up_date = models.DateTimeField(
        blank=True, null=True, verbose_name="Дата и время прибытия водителя"
    )
    start_ride_date = models.DateTimeField(
        blank=True, null=True, verbose_name="Дата начала поездки"
    )
    end_date = models.DateTimeField(
        blank=True, null=True, verbose_name="Дата завершения заказа"
    )
    entrance = models.CharField("Подъезд", blank=True, null=True, max_length=4)

    driver_not_accepted = models.ManyToManyField(to="cabinet.Driver", through="dispatcher.OrderDriverNotAccepted",
                                                 blank=True, null=True,
                                                 related_name="order_not_accepted"
                                                 )

    objects = OrderQuerySet.as_manager()

    def __str__(self):
        return "Заказ #%s" % self.pk

    def get_absolute_url(self):
        return reverse("cabinet:order", args=[self.pk])

    def get_status(self):
        # Аналог order.get_status_display()
        for code, status in ORDER_STATUSES:
            if code == self.status:
                return status

    class Meta:
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"
        ordering = ["-start_date"]

class OrderDriverNotAccepted(models.Model):
    driver = models.ForeignKey("cabinet.Driver", on_delete=models.CASCADE)
    order = models.ForeignKey(Order, on_delete=models.CASCADE)



class OrderRevision(models.Model):
    """
    Заказы, которые нужно перепроверять и найти водителей
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="revisions")
    end_date = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Заказы, которые нужно перепроверить"
        verbose_name_plural = "Заказы, которые нужно перепроверить"


class OrderReview(models.Model):
    """
    Отзыв, который клиент оставляет после поездки. Привязан к заказу
    """

    stars = models.IntegerField(choices=STARS_TYPES, verbose_name="Количество звёзд")
    text = models.TextField(
        max_length=1000, blank=True, null=True, verbose_name="Текст отзыва"
    )
    client = models.ForeignKey(User, related_name='review_list', on_delete=models.CASCADE, blank=True, null=True)
    driver = models.ForeignKey("cabinet.Driver", related_name='review_list', on_delete=models.CASCADE, blank=True, null=True)

    class Meta:
        verbose_name = "Отзыв на заказ"
        verbose_name_plural = "Отзывы на заказы"

    def __str__(self):
        return self.get_stars_display()


class Location(models.Model):
    """
    Геопозиция пользователя, хранит долготу и широту в градусах
    """

    point = models.PointField("Location in Map", srid=4326)
    date = models.DateTimeField(
        auto_now_add=True, verbose_name="Дата и время отправки геопозиции"
    )

    objects = LocationQuerySet.as_manager()

    def __str__(self):
        return "(%s, %s)" % self.as_tuple()

    def as_tuple(self) -> tuple:
        longitude, latitude = self.point.coords
        return (latitude, longitude)

    def as_json(self) -> dict:
        return {"latitude": self.point.coords[1], "longitude": self.point.coords[0]}

    def set_location(self, latitude: float, longitude: float) -> None:
        """
        Устанавливает переданные x, y значения как точку локации и автоматически сохранаяет
        """
        self.point = get_point_by_lat_lon(latitude=latitude, longitude=longitude)
        self.save()

    def get_base_location(self):
        return self.point

    class Meta:
        verbose_name = "Местоположение"
        verbose_name_plural = "Местоположения"


class AbstractCost(models.Model):
    """
    Абстрактная модель для стоимости
    """

    value = MoneyField()
    date = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    def __str__(self):
        return f"{self.value}"

    class Meta:
        abstract = True
        verbose_name = "Стоимость"
        verbose_name_plural = "Стоимости"
        ordering = ["-value"]

    # ordering by pk


class CostPerKm(AbstractCost):
    """
    Стоимость поездки за киллометр
    """

    night_allowance = MoneyField(
        default=30, verbose_name="Добавочная стоимость при ночном тарифе"
    )

    class Meta:
        verbose_name = "Стоимость за километр"
        verbose_name_plural = "Стоимости за километр"

    # ordering by pk


class CostPerBabyChair(AbstractCost):
    """
    Стоимость за десткое кресло
    """

    night_allowance = MoneyField(
        default=30, verbose_name="Добавочная стоимость при ночном тарифе"
    )

    class Meta:
        verbose_name = "Стоимость за десткое кресло"
        verbose_name_plural = "Стоимости за десткое кресло"


class City(models.Model):
    """
    Модель города. Хранит название города и стоимость за киллометр поездки
    """

    name = models.CharField(
        max_length=255, unique=True, db_index=True, verbose_name="Название города"
    )
    cost_per_km = models.OneToOneField(
        CostPerKm,
        on_delete=models.CASCADE,
        related_name="city",
        verbose_name="Стоимость за киллометр",
    )
    cost_per_baby_chair = models.OneToOneField(
        CostPerBabyChair,
        on_delete=models.CASCADE,
        related_name="city",
        default=DEFAULT_BABY_CHAIR_COST,
        verbose_name="Стоимость за детское кресло",
    )
    minimal_cost = MoneyField(
        default=MINIMAL_COST_OF_RIDE, verbose_name="Минимальная стоимость поездки"
    )
    timezone = TimeZoneField(default=TIME_ZONE, verbose_name="Часовой пояс")
    search_drivers_radius = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Радиус поиска водителей",
        help_text=f"Указывается в метрах. Если не указан, то будет применён радиус {SEARCH_NEAREST_DRIVERS_RADIUS}м.",
    )

    objects = CityQuerySet.as_manager()

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("cabinet:city_detail", args=[self.pk])

    def get_cost_per_km(self) -> "Decimal":
        return self.cost_per_km.value

    def get_minimal_cost(self) -> "Decimal":
        return self.minimal_cost

    def get_night_allowances(self) -> tuple:
        return (
            self.cost_per_km.night_allowance,
            self.cost_per_baby_chair.night_allowance,
        )

    def get_baby_chair_cost(self) -> "Decimal":
        return self.cost_per_baby_chair.value

    class Meta:
        verbose_name = "Город"
        verbose_name_plural = "Города"


class Address(models.Model):
    """
    Модель для хранения адреса
    """

    place_id = models.BigAutoField(primary_key=True)
    city = models.ForeignKey(
        City,
        on_delete=models.CASCADE,
        verbose_name="Город",
        related_name="addresses",
        db_index=True,
    )
    road = models.CharField(
        max_length=256, null=True, blank=True, verbose_name="Улица", db_index=True
    )
    house_number = models.CharField(
        max_length=16, null=True, blank=True, verbose_name="Номер дома", db_index=True
    )

    def __str__(self):
        return self.get_display_name()

    def get_display_name(self):
        """
        Возвращает в читабельном для клиента формате
        """
        if not self.road:
            return self.city.name
        else:
            if self.house_number:
                return self.city.name + ", %s, %s" % (self.road, self.house_number)
            else:
                return self.city.name + ", %s" % self.road


class Settings(models.Model):
    default_tariff_start = models.TimeField(
        verbose_name="Время начала стандартного тарифа"
    )
    default_tariff_end = models.TimeField(
        verbose_name="Время окончания стандартного тарифа",
        help_text="Максимальное значение: 23:59",
    )
    web_app_map_center = models.PointField(
        "Начальная точка на карте", default=Point(59.93521, 30.316447)
    )
    waiting_free_minutes = models.PositiveIntegerField(
        "Бесплатные минуты ожидания",
        default=3,
    )
    waiting_price = MoneyField(
        verbose_name="Цена за минуту ожидания",
        default=Decimal(3.0),
    )

    class Meta:
        verbose_name = "Настройки диспетчера"
        verbose_name_plural = verbose_name
        ordering = ["pk"]
