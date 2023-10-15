import logging

from django.db.models import Subquery, OuterRef, Exists, BooleanField
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework import generics, status, serializers
from rest_framework.decorators import permission_classes
from rest_framework.exceptions import ParseError, ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import ModelActionsPermission
from cabinet.models import User
from cabinet.utils.balance import update_user_balance
from cabinet.utils.driver import make_driver_active
from dispatcher.models import Settings as DispatcherSettings, Order
from dispatcher.serializers import SettingsSerializer as DispatcherSettingsSerializer
from dispatcher.serializers import UserLocationSerializer
from referral.serializers import CouponSerializer
from . import models
from .exceptions import USER_IS_REGISTERED
from .models import Settings as CabinetSettings
from .models import TelegramData
from .serializers import DriverRegisterSerializer, RegisterFromTelegramSerializer
from .serializers import SettingsSerializer as CabinetSettingsSerializer
from .serializers import (
    TelegramDataSerializer,
    TelegramUserAPISerializer,
    UserSerializer,
    UserUpdateBalanceSerializer,
)
from .utils.serializers import UserExtendedSerializer
from .utils.user import get_user_by_chat_id


class RegisterUserFromTelegramAPI(generics.GenericAPIView):
    """
    Вьюшка для регистрации пользователя через Telegram-бота
    """

    serializer_class = RegisterFromTelegramSerializer
    permission_classes = [ModelActionsPermission]
    queryset = TelegramData.objects.all()

    def post(self, request, *args, **kwargs):
        """
        POST запрос на создание нового пользователя
        """
        logging.info(f"Новый запрос на регистрацию пользователя: {request.data}")
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid(raise_exception=False):
            user = serializer.save()
            return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)
        else:
            if serializer.errors.get("chat_id"):
                raise ParseError(USER_IS_REGISTERED.code)
            else:
                raise ValidationError(serializer.errors)
            

class DriverRegisterAPI(APIView):


    def post(self, request, *args, **kwargs):
        chat_id = request.data.get("chat_id")
        user = get_user_by_chat_id(chat_id)

        serializer = DriverRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        driver = serializer.save()
        driver.photo = user.telegram_data.photo
        driver.save()
        user.driver = driver
        user.save()
        return Response(data=serializer.data, status=status.HTTP_201_CREATED)



class GetOrCreateUserFromTelegramAPI(generics.GenericAPIView):
    serializer_class = RegisterFromTelegramSerializer
    permission_classes = [ModelActionsPermission]
    queryset = TelegramData.objects.all()

    def post(self, request, *args, **kwargs):
        serializer = RegisterFromTelegramSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)
        else:
            user = TelegramData.objects.get(chat_id=serializer.data["chat_id"]).user
            return Response(UserSerializer(user).data, status=status.HTTP_200_OK)


class GetUserFromTelegramAPI(generics.GenericAPIView):
    serializer_class = TelegramDataSerializer
    permission_classes = [ModelActionsPermission]
    queryset = TelegramData.objects.all()

    def post(self, request):
        chat_id = request.data.get("chat_id")
        user = get_user_by_chat_id(chat_id)
        return Response(UserSerializer(user).data, status=status.HTTP_200_OK)


class GetUserApiByTelegramTokenAuth(APIView):
    class OutputSerilializer(serializers.ModelSerializer):
        coupons = CouponSerializer(read_only=True, many=True)
        has_active_order = serializers.BooleanField()

        class Meta:
            model = User
            fields = (
                "coupons",
                "has_active_order"
            )

    def get(self, request, token):
        user = User.objects.get(telegram_auth_token=token)
        user.has_active_order = Order.objects.in_progress().filter(client=user).exists()
        data = self.OutputSerilializer(
            user
        ).data
        return Response(data, status=status.HTTP_200_OK)


class UpdateUserAPIView(generics.UpdateAPIView):
    queryset = User.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer


class GetUserExtendedAPI(GetUserFromTelegramAPI):
    """
    Возвращает данные пользователя вместе с паролем
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        chat_id = request.data.get("chat_id")
        user = get_user_by_chat_id(chat_id)
        return Response(UserExtendedSerializer(user).data, status=status.HTTP_200_OK)


class OutOnTheLineDriver(APIView):
    """
    Выводит водителя на линию (делает активным) или выдает ошибку
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = TelegramUserAPISerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        chat_id = serializer.validated_data.get("chat_id")
        user = User.objects.select_related("balance", "driver").get(
            telegram_data__chat_id=chat_id
        )
        message = make_driver_active(driver=user)
        user.refresh_from_db()
        return JsonResponse({"user": UserSerializer(user).data, "message": message})


class GetAllSettingsAPIView(APIView):
    """
    Возвращает настройки проекта
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        dispatcher_settings = DispatcherSettings.objects.last()
        cabinet_settings = CabinetSettings.objects.last()

        return Response(
            {
                "dispatcher_settings": DispatcherSettingsSerializer(
                    dispatcher_settings
                ).data,
                "cabinet_settings": CabinetSettingsSerializer(cabinet_settings).data,
            },
            status=200,
        )


@csrf_exempt
@permission_classes([IsAuthenticated])
@require_http_methods(["POST"])
def finish_driver_work_day(request):
    data = JSONParser().parse(request)

    serializer = TelegramUserAPISerializer(data=data)
    serializer.is_valid(raise_exception=True)
    chat_id = serializer.validated_data.get("chat_id")
    user = User.objects.select_related("driver").get(telegram_data__chat_id=chat_id)
    user.driver.work_days.active().update(end_date=timezone.now())

    return JsonResponse(UserSerializer(user).data)


@csrf_exempt
@permission_classes([IsAuthenticated])
@require_http_methods(["PATCH"])
def update_users_location(request):
    """
    Принимает данные для обновления геопозиции сразу нескольких пользователей
    """
    data = JSONParser().parse(request)
    serializer = UserLocationSerializer(data=data, many=True)
    serializer.is_valid(raise_exception=True)
    chat_id_locations = {}

    # TODO: Переделать, ordered_dict нужно юзать по-другому, как в функции ниже
    for ordered_dict in serializer.validated_data:
        data = tuple(ordered_dict.values())
        chat_id_locations[data[0]] = data[1]
    users = User.objects.filter(
        telegram_data__chat_id__in=chat_id_locations
    ).select_related("telegram_data")
    for user in users:
        user.location = chat_id_locations.get(user.telegram_data.chat_id)

    a = User.objects.bulk_update(users, ["location"])

    return JsonResponse({"status": "ok"})


@csrf_exempt
@permission_classes([IsAuthenticated])
@require_http_methods(["POST"])
def update_user_balance_api_view(request):
    """
    Принимает данные для обновления баланса пользователя
    """
    data = JSONParser().parse(request)
    serializer = UserUpdateBalanceSerializer(data=data)
    if serializer.is_valid(raise_exception=False):
        # Обновляем баланс пользователя
        user_id = serializer.validated_data.get("pk")
        update_user_balance(
            user_id=user_id, value=serializer.validated_data.get("value"), field="money"
        )
        # Возвращаем положительный ответ
        return JsonResponse(
            UserSerializer(User.objects.get(pk=user_id)).data, status=status.HTTP_200_OK
        )
    else:
        # Возвращаем ответ с ошибками
        return JsonResponse(serializer.errors, status=400)
