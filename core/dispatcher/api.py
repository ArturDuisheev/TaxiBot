import datetime
import logging
from math import ceil
from django.conf import settings

from django.db.models import F
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import permission_classes
from rest_framework.exceptions import APIException, ParseError
from rest_framework.generics import UpdateAPIView
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import HttpRequest
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers, status

from cabinet.models import Settings as CabinetSettings, Driver, SettingsDriverMessageBan
from cabinet.models import User
from cabinet.utils.driver import check_driver
from cabinet.serializers import DriverSerializer, TelegramUserAPISerializer
from dispatcher.tasks import driver_not_accepted_clear
from dispatcher.utils.geolocator import get_address_by_location
from dispatcher.utils.order import get_cost_of_order, set_driver_to_order
from referral.models import Coupon
from referral.utils.coupon import give_coupon_to_user
from . import settings as dispatcher_settings
from .exceptions import (
    NOT_VALID_STATUS,
    ORDER_CANCELED_BY_CLIENT_ERROR,
    USER_DONT_HAVE_ORDER,
)
from .models import Location, Order, OrderRevision, Settings as DispatcherSettings
from .serializers import (
    CreateOrderSerializer,
    DriverPickOrderSerializer,
    GetActiveOrderSerializer,
    LocationSerializer,
    OrderReviewSerializer,
    OrderSerializer,
    ReCreateOrderSerializer,
    UpdateOrderReviewSerializer,
    UpdateOrderStatusSerializer,
    SettingsSerializer as DispatcherSettingsSerializer,
    SettingsOnlyWebAppMapCenterSerializer,
)
from .settings import IN_PROGRESS_STATUSES, ORDER_CANCELED_BY_CLIENT, WAIT_TO_ACCEPT


class CreateOrderAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Проверяет данные и создает объект заказа.
        Возвращает сериализированный объект с найденными водителями и стоимостью
        """
        serializer = CreateOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = serializer.save()

        return Response(OrderSerializer(order).data)


class ReCreateOrderAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Создает копию заказа, заново находит водителей
        """
        serializer = ReCreateOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        return Response(OrderSerializer(order).data)


class UpdateOrderAPI(UpdateAPIView):
    permission_classes = [IsAuthenticated]
    queryset = Order.objects.all()
    serializer_class = OrderSerializer


class DriverPickOrderAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: HttpRequest):
        serializer = DriverPickOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        chat_id = serializer.validated_data.get("chat_id")
        order_id = serializer.validated_data.get("order_id")
        user = User.objects.select_related("driver", "location").get(
            telegram_data__chat_id=chat_id
        )
        check_driver(user)

        order = Order.objects.get(pk=order_id)
        if order.status not in IN_PROGRESS_STATUSES:
            if order.status == ORDER_CANCELED_BY_CLIENT:
                raise ParseError(ORDER_CANCELED_BY_CLIENT_ERROR)
            else:
                raise ParseError(USER_DONT_HAVE_ORDER)
        order = set_driver_to_order(order, user)

        return Response(OrderSerializer(order).data)


class UpdateOrderStatusAPI(APIView):
    """
    Обновляет статус заказа и делает соответствующие изменения в заказе
    Например: ставит дату подъезда водителя
    """

    permission_classes = [IsAuthenticated]

    def patch(self, request: HttpRequest, order_id):
        serializer = UpdateOrderStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        status = data.get("status")

        status_is_valid = False
        for status_code, str_status in dispatcher_settings.ORDER_STATUSES:
            if status_code == status:
                status_is_valid = True

        if not status_is_valid:
            raise ParseError(NOT_VALID_STATUS)

        order: Order = Order.objects.select_related("coupon", "client").get(pk=order_id)
        if order.status not in dispatcher_settings.IN_PROGRESS_STATUSES:
            raise ParseError(USER_DONT_HAVE_ORDER)

        if status < order.status:
            raise ParseError(NOT_VALID_STATUS)

        order.status = status

        if status == dispatcher_settings.DRIVER_IS_WAITING:
            # Когда водитель подъехал и ожидает клиента
            order.pull_up_driver_location = order.driver.location
            order.driver_pull_up_date = timezone.now()

        if status == dispatcher_settings.RIDE_IS_STARTED:
            # Когда клиент сел в машину и водитель начал поездку
            order.start_ride_date = timezone.now()
            d_settings = DispatcherSettings.objects.last()
            rub_for_minute = d_settings.waiting_price
            free_minutes = d_settings.waiting_free_minutes
            # Получаем время ожидания
            waiting_time: datetime.timedelta = (
                    order.start_ride_date - order.driver_pull_up_date
            )
            if waiting_time > datetime.timedelta(minutes=free_minutes):
                # Если время ожидания больше заданного, то считаем наценку
                # Берем кол-во минут с округлением в большую сторону
                waiting_minutes = ceil(waiting_time.total_seconds() / 60)
                # Прибавляем к стоимости заказа наценку
                order.cost += (waiting_minutes - free_minutes) * rub_for_minute

        if status == dispatcher_settings.RIDE_IS_FINISHED:
            # Когда поездка окончена
            order.end_date = timezone.now()

            if order.coupon:
                # Если к заказу применен купон
                # Убираем купон из купонов клиента
                order.client.coupons.remove(order.coupon)
                # Добавляем купон в использованные купоны клиента
                order.client.used_coupons.add(order.coupon)

            if order.client.orders.count() <= 1 and order.client.mentor:
                # Если это первая поездка человека и он приглашенный
                # То выдаем ментору купон
                try:
                    give_coupon_to_user(
                        user=order.client.mentor,
                        coupon=CabinetSettings.objects.last().mentor_coupon,
                    )
                except Exception as E:
                    logging.warning(
                        f"Не удалось выдать купон ментору при завершении поездки: {E.args}"
                    )

        order.save()
        return JsonResponse(OrderSerializer(order).data)


class GetActiveOrderByTelegramAuthToken(APIView):

    class OutputSerializer(serializers.ModelSerializer):
        class UserDriverSerializer(serializers.Serializer):
            class DriverSerializer(serializers.ModelSerializer):
                class CarSerializer(serializers.Serializer):
                    brand = serializers.CharField(source="brand.name")
                    color = serializers.CharField()
                    number = serializers.CharField()

                car = CarSerializer()
                photo_url = serializers.SerializerMethodField()

                def get_photo_url(self, instance):
                    return settings.BASE_URL + instance.photo.url

                class Meta:
                    model = Driver
                    fields = (
                        "photo_url",
                        "car",
                    )

            first_name = serializers.CharField()
            last_name = serializers.CharField()
            driver = DriverSerializer()
            location = LocationSerializer()

        start_location = LocationSerializer()
        end_location = LocationSerializer()
        driver = UserDriverSerializer()

        class Meta:
            model = Order
            fields = (
                "start_location",
                "end_location",
                "driver",
                "cost",
                "address",
                "status",
            )

    def get(self, request, token):
        order = (
            Order.objects.filter(
                client__telegram_auth_token=token,
            )
            .select_related(
                "driver",
                "driver__location",
                "driver__driver",
                "driver__driver__car",
                "driver__driver__car__brand"
            )
            .in_progress().last()
        )
        return Response(
            self.OutputSerializer(order).data,
            status=status.HTTP_200_OK,
        )


@csrf_exempt
@permission_classes([IsAuthenticated])
@require_http_methods(["POST"])
def get_active_order_api_view(request: HttpRequest):
    """
    Возвращает активный заказ пользователя или ошибку
    """

    data = JSONParser().parse(request)
    serializer = GetActiveOrderSerializer(data=data)
    if serializer.is_valid():
        data = serializer.validated_data
        client_chat_id = data.get("chat_id")

        order = (
            Order.objects.select_related(
                "client",
                "client__telegram_auth_token",
                "driver",
                "driver__telegram_auth_token",
                "address",
                "finish_address",
                "coupon",
                "start_location",
                "end_location",
            )
            .filter(
                client__telegram_data__chat_id=client_chat_id,
                status__in=IN_PROGRESS_STATUSES,
            )
            .last()
        )
        if not order:
            return JsonResponse({"detail": USER_DONT_HAVE_ORDER}, status=404)

        return JsonResponse(OrderSerializer(order).data)
    else:
        return JsonResponse(serializer.errors)


@csrf_exempt
@permission_classes([IsAuthenticated])
@require_http_methods(["POST"])
def get_active_ride_api_view(request: HttpRequest):
    """
    Возвращает активный заказ пользователя или ошибку
    """

    data = JSONParser().parse(request)
    serializer = GetActiveOrderSerializer(data=data)
    if serializer.is_valid():
        data = serializer.validated_data
        client_chat_id = data.get("chat_id")

        order = (
            Order.objects.select_related("client")
            .filter(
                driver__telegram_data__chat_id=client_chat_id,
                status__in=IN_PROGRESS_STATUSES,
            )
            .last()
        )
        if not order:
            return JsonResponse({"detail": USER_DONT_HAVE_ORDER}, status=404)

        return JsonResponse(OrderSerializer(order).data)
    else:
        return JsonResponse(serializer.errors)


@csrf_exempt
@permission_classes([IsAuthenticated])
@require_http_methods(["POST"])
def set_order_review(request: HttpRequest):
    """
    Принимает запрос на обновление отзыва у заказа
    """
    data = JSONParser().parse(request)
    serializer = UpdateOrderReviewSerializer(data=data)
    if serializer.is_valid():
        review = serializer.save()
        return JsonResponse(OrderReviewSerializer(review).data)
    else:
        return JsonResponse(serializer.errors)


@csrf_exempt
@permission_classes([IsAuthenticated])
@require_http_methods(["POST"])
def create_order_revision_api_view(request: HttpRequest):
    """
    Принимает запрос на заказ, в котором нужно перепроверить водителей
    """
    data = JSONParser().parse(request)
    order_id = data.get("order_id")
    if not order_id:
        return JsonResponse({"detail": "bad_request"})

    now = timezone.now()
    order_revision = OrderRevision.objects.create(
        order_id=order_id, is_active=True, end_date=now + datetime.timedelta(minutes=10)
    )
    order_revision.save()
    return JsonResponse({"status": "ok"})


@csrf_exempt
# @require_http_methods(["POST"])
def get_price_api_view(request):
    if request.method != "POST":
        return JsonResponse({})
    data = JSONParser().parse(request)
    start_location = LocationSerializer(data=data["start_location"])
    if not start_location.is_valid():
        return JsonResponse({"detail": "invalid_start_address"}, status=400)
    end_location = LocationSerializer(data=data["end_location"])
    if not end_location.is_valid():
        return JsonResponse({"detail": "invalid_end_address"}, status=400)

    start_location = Location.objects.serialize_init(start_location.data)
    end_location = Location.objects.serialize_init(end_location.data)

    coupon = None
    if c_id := data.get("coupon_id"):
        coupon = Coupon.objects.get(id=c_id)

    try:
        address = get_address_by_location(start_location)
        cost, raw_cost = get_cost_of_order(
            start_location,
            end_location,
            city=address.city,
            is_need_baby_chair=data.get("baby_chair"),
            coupon=coupon,
        )  # type: ignore
    except APIException as E:
        return JsonResponse({"detail": E.detail}, status=400)

    return JsonResponse({"cost": cost, "raw_cost": raw_cost})


class GetMapCenterAPIView(APIView):
    permission_classes = []

    def get(self, request):
        settings = DispatcherSettings.objects.last()
        serializer = SettingsOnlyWebAppMapCenterSerializer(settings)

        return JsonResponse(serializer.data)


class DriverAnalyticsOrderAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        
        serializers = TelegramUserAPISerializer(data=request.data)
        serializers.is_valid(raise_exception=True)
        
        user = User.objects.select_related("balance", "driver").get(
            telegram_data__chat_id=serializers.validated_data.get("chat_id")
        )
        check_driver(user)
        order = get_object_or_404(Order.objects.only("id"), id=pk)
        if WAIT_TO_ACCEPT != order.status:
            return JsonResponse({"detail": "order status is not Wait To Accept"}, status=status.HTTP_400_BAD_REQUEST)
        else:
            if not user.driver.order_not_accepted.filter(id=order.id).exists():
                try:
                    settings_driver_blocked = SettingsDriverMessageBan.objects.last()
                    minute = settings_driver_blocked.count_minute_blocked
                    count = settings_driver_blocked.count_not_accepted
                except:
                    minute = 5
                    count = 5
                user.driver.order_not_accepted.add(order)
                if count == user.driver.count_not_accepted + 1:
                    date = datetime.datetime.now() + datetime.timedelta(minutes=minute)
                    
                    user.driver.time_blocked_message_order = date
                    date_str = date.strftime('%m/%d/%Y, %H:%M:%S')
                    data = {"message":f"Вы заблокированны до {date_str}", "is_block": True}
                    driver_not_accepted_clear.apply_async(kwargs={"driver_id": user.driver.id}, countdown= minute * 60)
                elif count < user.driver.count_not_accepted + 1:
                    if user.driver.time_blocked_message_order is None:
                        date = datetime.datetime.now() + datetime.timedelta(minutes=minute)
                    else:
                        date = user.driver.time_blocked_message_order
                    date_str = date.strftime('%m/%d/%Y, %H:%M:%S')
                    data = {"message":f"Вы заблокированны до {date_str}", "is_block": True}
                else:
                    
                    user.driver.count_not_accepted += 1
                    data = {"message":f"count not accepted: {user.driver.count_not_accepted}", "is_block": False}
                user.driver.save()
                return JsonResponse({"detail": data}, status=status.HTTP_200_OK)
            else:
                return JsonResponse({"detail": "order is not accepted"}, status=status.HTTP_400_BAD_REQUEST)
