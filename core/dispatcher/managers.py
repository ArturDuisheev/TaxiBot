from typing import Optional

from cabinet.models import User
from django.contrib.gis.db.models import Q, QuerySet
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from .exceptions import CityNotFound
from .settings import IN_PROGRESS_STATUSES


class OrderQuerySet(QuerySet):
    def in_progress(self):
        return self.filter(status__in=IN_PROGRESS_STATUSES)

    def finished(self):
        return self.exclude(status__in=IN_PROGRESS_STATUSES)

    def with_review(self):
        return self.filter(review__isnull=False)


class CityQuerySet(QuerySet):
    """
    Используется для инициализии менеджера объектов
    """

    def get_city_by_name(self, name: str) -> Optional["City"]:
        """
        Выдыает объект города по его названию
        """
        try:
            city = self.get(name=name)
        except ObjectDoesNotExist:
            # Если города с таким названием нет в базе данных
            print(f"Город {name!r} не обслуживается.")
            raise CityNotFound("city_not_registered")
        return city

    # def get_city_by_location(self, location: "Location") -> Optional["City"]:
    #     """
    #         Возвращает город по геопозиции
    #     """
    #     name = get_city_name_by_location(location = location)
    #     city = self.get_city_by_name(name = name)
    #
    #     return city


class LocationQuerySet(QuerySet):
    def serialize_init(self, data: "OrderedDict") -> "Location":
        """
            Возвращает объект Location по данным LocationSerializer
        :param data:
        :return:
        """
        point = get_point_by_lat_lon(data["latitude"], data["longitude"])
        return self.create(point=point)


def get_point_by_lat_lon(latitude, longitude) -> Point:
    return Point(longitude, latitude, srid=4326)


def get_closest_drivers_by_location(
    user: User,
    location: "Location",
    radius: "in meters" = 30000,
    max_count: int = 15,
    baby_chair=False,
) -> QuerySet:
    base_location = location.get_base_location()
    bad_orders = user.get_bad_orders()
    time_now = timezone.now()
    filter = Q(
        driver__isnull=False,
        driver__work_days__end_date__gt=time_now,
        location__point__distance_lte=(base_location, D(m=radius)),
        driver__time_blocked_message_order__lt=time_now,
    )
    filter_add = Q(driver__time_blocked_message_order__lt=time_now)
    if baby_chair:
        # Если нужно детское кресло, то добавляет это к запросу
        filter &= Q(driver__baby_chair=baby_chair)

    


    drivers = (
        User.objects.select_related("location", "driver")
        .filter(filter, filter_add | Q(driver__time_blocked_message_order__isnull=True))
        .exclude(rides__in=bad_orders)
        .exclude(telegram_data__chat_id=user.telegram_data.chat_id)
        .annotate(distance=Distance("location__point", base_location))
        .order_by("distance")[:max_count]
    )

    print("Водителей найдено: ", drivers.count())
    print("Радиус: ", radius, "м")

    return drivers
