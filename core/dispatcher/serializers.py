from cabinet.models import Driver
from referral.serializers import CouponSerializer
from rest_framework import serializers
from rest_framework_gis.fields import GeometryField
from rest_framework.exceptions import ParseError
from rest_framework.validators import ValidationError
from dispatcher.models import Order, OrderReview

from .exceptions import CLIENT_ALREADY_HAS_ORDER, BadRequest
from .managers import get_closest_drivers_by_location
from .models import Address, City, Location, Settings
from .settings import ORDER_IS_CREATED, SEARCH_NEAREST_DRIVERS_RADIUS
from .utils.geolocator import get_address_by_location
from .utils.order import create_order


class LocationSerializer(serializers.Serializer):
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()

    def to_representation(self, instance):
        ret = instance.as_json()
        return ret

    def to_internal_value(self, data):
        try:
            return Location.objects.serialize_init(data)
        except KeyError:
            raise BadRequest("Ошибка в переданных данных объекта Location")


class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        exclude = ("timezone",)


class AddressSerializer(serializers.ModelSerializer):
    city = CitySerializer()

    class Meta:
        model = Address
        fields = "__all__"


class OrderReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderReview
        fields = "__all__"


class OrderSerializer(serializers.ModelSerializer):
    from cabinet.serializers import UserSerializer

    suitable_drivers = UserSerializer(many=True)
    client = UserSerializer()
    driver = UserSerializer()
    address = AddressSerializer()
    finish_address = AddressSerializer()
    coupon = CouponSerializer()
    review = OrderReviewSerializer()

    start_location = LocationSerializer()
    end_location = LocationSerializer()
    start_driver_location = LocationSerializer()
    pull_up_driver_location = LocationSerializer()

    class Meta:
        model = Order
        fields = "__all__"


class OrderDashboardSerializer(serializers.ModelSerializer):
    start_location = LocationSerializer()
    end_location = LocationSerializer()

    class Meta:
        model = Order
        fields = (
            "start_location",
            "end_location",
            "cost",
            "status",
            "start_date",
            "end_date",
        )


class CreateOrderSerializer(serializers.ModelSerializer):
    start_location = LocationSerializer()
    end_location = LocationSerializer()
    comment = serializers.CharField(allow_null=True, max_length=1000, allow_blank=True)
    entrance = serializers.CharField(allow_null=True, max_length=4)

    class Meta:
        model = Order
        fields = (
            "client",
            "coupon",
            "start_location",
            "end_location",
            "payment_method",
            "client_phone",
            "is_need_baby_chair",
            "comment",
            "entrance",
        )

    def create(self, validated_data):
        # start_location = Location.objects.serialize_init(validated_data.get('start_location'))
        # end_location = Location.objects.serialize_init(validated_data.get('end_location'))
        start_location, end_location = validated_data.get(
            "start_location"
        ), validated_data.get("end_location")
        address = get_address_by_location(location=start_location)

        try:
            finish_address = get_address_by_location(location=end_location)
        except Exception:
            finish_address = None

        client = validated_data.get("client")

        if not client.can_create_order:
            raise ParseError(CLIENT_ALREADY_HAS_ORDER)

        order = create_order(
            client=client,
            start_location=start_location,
            end_location=end_location,
            payment_method=validated_data.get("payment_method"),
            client_phone=validated_data.get("client_phone"),
            address=address,
            finish_address=finish_address,
            coupon=validated_data.get("coupon"),
            is_need_baby_chair=validated_data.get("is_need_baby_chair") or False,
            comment=validated_data.get("comment"),
            entrance=validated_data.get("entrance"),
        )

        return order


class ReCreateOrderSerializer(serializers.Serializer):
    order_id = serializers.IntegerField()

    def create(self, validated_data):
        base_order_id = validated_data.get("order_id")
        base_order = Order.objects.select_related(
            "start_location", "end_location", "client"
        ).get(pk=base_order_id)

        if not base_order.client.can_create_order:
            raise ParseError(CLIENT_ALREADY_HAS_ORDER)

        order = base_order
        order.pk = None
        start_location = base_order.start_location
        start_location.pk = None
        start_location.save()
        end_location = base_order.end_location
        end_location.pk = None
        end_location.save()
        order.review = None
        order.start_location = start_location
        order.end_location = end_location
        order.save()

        order.save()

        drivers = get_closest_drivers_by_location(
            user=order.client,
            location=order.start_location,
            baby_chair=order.is_need_baby_chair,
            radius=order.address.city.search_drivers_radius
                   or SEARCH_NEAREST_DRIVERS_RADIUS,
        )

        if drivers:
            order.status = ORDER_IS_CREATED
            order.suitable_drivers.set(drivers)

        order.save()
        return order


class GetActiveOrderSerializer(serializers.Serializer):
    """
    Для получения незавершенного заказа
    """

    chat_id = serializers.IntegerField()


class UserLocationSerializer(serializers.Serializer):
    """
    Сериализирует данные, которые передаются при обновлении пользователя
    """

    chat_id = serializers.IntegerField()  # telegram_data chat_id
    location = LocationSerializer()

    def create(self, validated_data):
        """
            Обновляет информацию обо всех водителях
        :param validated_data:
        :return:
        """
        print(validated_data)
        # data = {chat_id: location for chat_id, location in validated_data.values()}
        # users = User.objects.filter(telegram_data__chat_id__in=data).select_related('telegram_data')
        # for user in users:
        #     user.location = data.get(user.telegram_data.chat_id)
        #
        # users.bulk_update(['location'])
        return None


class DriverPickOrderSerializer(serializers.Serializer):
    """
    Если водитель хочет принять заказ
    """

    chat_id = serializers.IntegerField()
    order_id = serializers.IntegerField()


class UpdateOrderStatusSerializer(serializers.Serializer):
    """
    Обновление статуса заказа
    """

    status = serializers.IntegerField()


class UpdateOrderReviewSerializer(serializers.Serializer):
    """
    Обновление отзыва о заказе
    """

    order_id = serializers.IntegerField()
    review = OrderReviewSerializer()

    def create(self, validated_data):
        order_id = validated_data.get("order_id")
        review_raw = validated_data.get("review")
        order = Order.objects.get(pk=order_id)
        order_review = OrderReview(**review_raw)
        order_review.save()
        order.review = order_review
        order.save()
        print("Оставлен отзыв к поездке #", order_id)
        return order_review


class OrderRevisionNotifySerializer(serializers.Serializer):
    chat_id = serializers.SerializerMethodField()
    order_id = serializers.SerializerMethodField()

    def get_chat_id(self, instance):
        return instance.client.telegram_data.chat_id

    def get_order_id(self, instance):
        return instance.pk


class SettingsSerializer(serializers.ModelSerializer):
    web_app_map_center = GeometryField()

    class Meta:
        model = Settings
        fields = "__all__"


class SettingsOnlyWebAppMapCenterSerializer(serializers.Serializer):
    web_app_map_center = GeometryField()

