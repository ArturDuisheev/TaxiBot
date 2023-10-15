import logging

from cabinet.utils.balance import update_user_balance
from dispatcher.serializers import LocationSerializer
from django.conf import settings
from referral.serializers import CouponSerializer
from rest_framework import serializers
from rest_framework.settings import import_from_string

from . import models


class TelegramDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.TelegramData
        fields = "__all__"
        read_only_fields = ("user",)


class BalanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Balance
        fields = ("money", "bonuses", "free_days")


class CarBrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.CarBrand
        fields = "__all__"


class CarSerializer(serializers.ModelSerializer):
    brand = CarBrandSerializer()

    class Meta:
        model = models.Car
        fields = "__all__"


class DriverSerializer(serializers.ModelSerializer):
    car = CarSerializer()
    is_active = serializers.SerializerMethodField()
    photo_url = serializers.SerializerMethodField()

    def get_is_active(self, instance):
        return instance.is_active

    def get_photo_url(self, instance):
        return settings.BASE_URL + instance.photo.url

    class Meta:
        model = models.Driver
        fields = "__all__"



class DriverRegisterSerializer(serializers.ModelSerializer):
    car = CarSerializer()
    
    class Meta:
        model = models.Driver
        fields = "__all__"

    def create(self, validated_data):
        brand_car = models.CarBrand.objects.create(**validated_data["car"].pop("brand"))
        car = models.Car.objects.create(**validated_data.pop("car"), brand_id=brand_car.id)

        instance = models.Driver.objects.create(**validated_data, car_id=car.id)
        return instance


class WorkDriverDaySerializer(serializers.ModelSerializer):
    class Meta:
        fields = "__all__"
        model = models.WorkDriverDay


class UserSerializer(serializers.ModelSerializer):
    coupons = CouponSerializer(read_only=True, many=True)
    balance = serializers.SerializerMethodField()
    driver = DriverSerializer()
    telegram_data = TelegramDataSerializer()
    location = LocationSerializer()
    telegram_auth_token = serializers.SerializerMethodField()

    class Meta:
        model = models.User
        fields = "__all__"
        extra_kwargs = {"password": {"write_only": True}}

    def get_balance(self, user: models.User):
        return BalanceSerializer(user.balance).data

    def get_telegram_auth_token(self, instance):
        return instance.telegram_auth_token.key







class RegisterFromTelegramSerializer(serializers.ModelSerializer):
    """
    Регистрация нового пользователя через Telegram бота
    """

    first_name = serializers.CharField(max_length=255)
    mentor_chat_id = serializers.IntegerField(allow_null=True, required=False)

    class Meta:
        model = models.TelegramData
        exclude = ("user",)

    def create(self, validated_data, *args, **kwargs):
        """
        Вызывается при serializer.save()
        Создает нового пользователя на основе данных из Телеграмма
        Генерирует случайный пароль и юзернейм на основе шаблона (username1, username12 etc)
        """
        password = models.User.objects.make_random_password()
        username = models.User.objects.make_username(
            template=validated_data.get("username")
        )
        mentor, coupon = (None, None)
        photo = validated_data.get("photo")
        if validated_data.get("mentor_chat_id"):
            try:
                mentor = models.User.objects.get(
                    telegram_data__chat_id=validated_data.get("mentor_chat_id")
                )
                coupon = models.Settings.objects.last().hirer_coupon
            except models.User.DoesNotExist:
                pass
        user = models.User.objects.create_user(
            first_name=validated_data.get("first_name"),
            username=username,
            password=password,
            mentor=mentor,
        )
        if coupon:
            user.coupons.add(coupon)
        telegram_data = models.TelegramData.objects.create(
            user=user,
            username=validated_data.get("username"),
            chat_id=validated_data.get("chat_id"),
        )

        if photo:
            telegram_data.photo = photo
            telegram_data.save()

        logging.info(
            f">> Зарегистрирован {user}, {mentor=}, {telegram_data.pk=}, {coupon=}, {telegram_data.photo=}"
        )
        print(
            f">> Зарегистрирован {user}, {mentor=}, {telegram_data.pk=}, {coupon=}, {telegram_data.photo=}"
        )
        return user


class UserUpdateBalanceSerializer(serializers.Serializer):
    """
    Сериализует данные для обновления баланса пользователя
    """

    pk = serializers.IntegerField()
    value = serializers.DecimalField(max_digits=10, decimal_places=2)

    def create(self, validated_data):
        pk = validated_data.get("pk")
        value = validated_data.get("value")
        update_user_balance(user_id=pk, value=value)


class UserAPISerializer(serializers.Serializer):
    """
    Возвращает объект пользователя по его ID
    """

    pk = serializers.IntegerField()

    def create(self, validated_data):
        user = models.User.objects.get(pk=validated_data["pk"])

        return user


class TelegramUserAPISerializer(serializers.Serializer):
    chat_id = serializers.IntegerField()

    def create(self, validated_data):
        return models.User.objects.get(telegram_data__chat_id=validated_data["chat_id"])


class SettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Settings
        fields = "__all__"
