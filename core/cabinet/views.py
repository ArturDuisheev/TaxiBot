import logging

from django.db.models import Avg
from django.conf import settings as config
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.views import LoginView as BaseLoginView
from django.http import HttpRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django_tables2 import RequestConfig
from django_tables2.export.export import TableExport

from cabinet.models import Car, CarBrand
from cabinet.models import Settings as CabinetSettings
from cabinet.models import User
from cabinet.utils.serializers import UserExtendedSerializer
from dispatcher.forms import (
    CityForm,
    CostPerBabyChairForm,
    CostPerKmForm,
    CreateCityForm,
)
from dispatcher.forms import SettingsForm as DispatcherSettingsForm
from dispatcher.models import City, CostPerBabyChair, CostPerKm, Order
from dispatcher.models import Settings as DispatcherSettings
from dispatcher.serializers import OrderDashboardSerializer
from dispatcher.tables import AdminOrdersTable, CityTable, DriverOrdersTable
from referral.forms import (
    CouponForm,
    CreateCouponForm,
    CreateMailingForm,
    CreateMessageForm,
    CreateRaffleForm,
    MailingForm,
    MessageForm,
)
from referral.models import Coupon, Mailing, Message, Raffle
from referral.serializers import MessageSerializer
from referral.tables import (
    CouponsDriverTable,
    CouponsTable,
    MailingTable,
    MessageTable,
    RaffleTable,
)
from referral.tasks import send_mailing_to_bot
from referral.utils.coupon import apply_coupon, give_coupon_to_user
from referral.utils.mailing import initialize_mailing
from .filters import UserFilter
from .forms import BalanceForm, BanUserForm, DriverForm
from .forms import SettingsForm as CabinetSettingsForm
from .forms import TelegramDataForm, UserForm
from .tables import UsersListTable


class LoginView(BaseLoginView):
    template_name = "cabinet/login.html"
    redirect_authenticated_user = True


def telegram_auth_token_login(request, token: str):
    try:
        user = User.objects.get(telegram_auth_token=token)
    except User.DoesNotExist:
        return redirect(config.LOGIN_URL)
    login(request, user)
    return redirect(config.LOGIN_REDIRECT_URL)


def logout_view(request: HttpRequest):
    if request.user.is_authenticated:
        logout(request)
    return redirect("cabinet:login")


@login_required()
def index_view(request: HttpRequest):
    context = {"user_data": UserExtendedSerializer(request.user).data}
    return render(request, "cabinet/index.html", context)


@login_required()
def orders_view(request: HttpRequest):
    # Возвращает таблицу со всеми заказами, применяет пагинацию
    table = DriverOrdersTable(request.user.rides.finished())

    RequestConfig(request, paginate={"per_page": 25}).configure(table)
    export_format = request.GET.get("_export", None)
    if TableExport.is_valid_format(export_format):
        exporter = TableExport(export_format, table)
        return exporter.response("users-{}.{}".format(timezone.now(), export_format))

    context = {"table": table}
    return render(request, "cabinet/forms/order/orders.html", context)


@login_required()
def order_detail_driver_view(request: HttpRequest, pk: int):
    # Открывает страницу поездки для водителя
    is_has_perm = request.user.has_perm("dispatcher.view_order")
    logging.info(f"{is_has_perm=} | {pk=}")
    if is_has_perm:
        orders = Order.objects.all()
    else:
        orders = request.user.rides.finished()
    order = get_object_or_404(orders, pk=pk)
    context = {"order": order}

    return render(request, "cabinet/forms/order/order_detail_driver.html", context)


@login_required()
@permission_required("cabinet.view_user", raise_exception=True)
def users_list_view(request: HttpRequest):
    # Открывает список пользователей
    filter = UserFilter(
        request.GET, queryset=User.objects.select_related("telegram_data").all()
    )
    table = UsersListTable(filter.qs)
    RequestConfig(request, paginate={"per_page": 25}).configure(table)
    export_format = request.GET.get("_export", None)
    if TableExport.is_valid_format(export_format):
        exporter = TableExport(export_format, table)
        return exporter.response("users-{}.{}".format(timezone.now(), export_format))

    context = {"table": table, "filter": filter, "form_helper": UserForm.helper}

    return render(request, "cabinet/forms/user/users_list.html", context)


@login_required()
@permission_required("cabinet.change_user", raise_exception=True)
def user_detail_view(request: HttpRequest, pk: int):
    logging.info(f"Началось обновление пользователя, обновляет {request.user.pk=}")
    user = get_object_or_404(
        User.objects.select_related(
            "driver", "balance", "telegram_data", "driver__car", "driver__car__brand"
        ).annotate(Avg('review_list__stars')),
        pk=pk,
    )
    logging.info(f"Пользователь получен из базы данных {user.pk=}")

    user_form = UserForm(instance=user)
    balance_form = BalanceForm(instance=user.balance)
    if user.driver:
        driver_form = DriverForm(
            instance=user.driver,
            initial={
                "car_brand": user.driver.car.brand.name,
                "car_color": user.driver.car.color,
                "car_number": user.driver.car.number,
            },
        )
    else:
        driver_form = DriverForm()
    telegram_data_form = TelegramDataForm(instance=user.telegram_data)
    logging.info("Формы сгенерированы")

    ban_form = BanUserForm()
    if request.method == "POST":
        logging.info(f"user_detail_view POST-запрос {request.POST=}, {request.FILES=}")

        if "submit__user" in request.POST:
            # Если сохранить пользователя
            user_form = UserForm(request.POST, request.FILES, instance=user)
            if user_form.is_valid():
                user_form.save()

        elif "delete__user" in request.POST and request.user.has_perm(
            "cabinet.delete_user"
        ):
            user.delete()
            return redirect("cabinet:users")

        elif "submit__balance" in request.POST and request.user.has_perm(
            "cabinet.change_balance"
        ):
            # Если сохранить баланс
            balance_form = BalanceForm(request.POST, instance=user.balance)
            if balance_form.is_valid():
                balance_form.save()

        elif "submit__driver" in request.POST and request.user.has_perm(
            "cabinet.change_driver"
        ):
            # 		Если сохранить воданные водителя
            driver_form = DriverForm(request.POST, request.FILES, instance=user.driver)
            if driver_form.is_valid():
                driver = driver_form.save(commit=False)
                data = driver_form.cleaned_data
                brand = CarBrand.objects.filter(name=data["car_brand"]).first()
                if not brand:
                    brand = CarBrand(name=data["car_brand"])
                    brand.save()
                driver.car = Car(
                    brand=brand, color=data["car_color"], number=data["car_number"]
                )
                user.driver = driver
                user.driver.car.save()
                user.driver.save()
                user.save()

        elif "delete__driver" in request.POST and request.user.has_perm(
            "cabinet.delete_driver"
        ):
            driver = user.driver
            driver.delete()
            driver_form = DriverForm()

        elif "submit__telegram_data" in request.POST and request.user.has_perm(
            "cabinet.change_telegram_data"
        ):
            telegram_data_form = TelegramDataForm(
                request.POST, request.FILES, instance=user.telegram_data
            )
            if telegram_data_form.is_valid():
                telegram_data_form.save()

        elif "ban__user" in request.POST and request.user.has_perm("cabinet.add_ban"):
            ban_form = BanUserForm(request.POST)
            if ban_form.is_valid():
                ban = ban_form.save(commit=False)
                ban.user = user
                ban.save()
                messages.success(request, "Пользователь заблокирован!")

        elif "unban__user" in request.POST and request.user.has_perm(
            "cabinet.delete_ban"
        ):
            user.unban()
            messages.success(request, "Все блокировки сняты!")

    logging.info("Генерируется контекст...")

    context = {
        "user": user,
        "user_form": user_form,
        "balance_form": balance_form,
        "driver_form": driver_form,
        "telegram_data_form": telegram_data_form,
        "ban_form": ban_form,
    }

    return render(request, "cabinet/forms/user/user_detail.html", context)


@login_required()
@permission_required("dispatcher.view_order", raise_exception=True)
def orders_list_admin_view(request: HttpRequest):
    # Возвращает таблицу со всеми заказами, применяет пагинацию
    table = AdminOrdersTable(Order.objects.all())

    RequestConfig(request, paginate={"per_page": 25}).configure(table)
    export_format = request.GET.get("_export", None)
    if TableExport.is_valid_format(export_format):
        exporter = TableExport(export_format, table)
        return exporter.response("orders_history.{}".format(export_format))

    context = {"table": table}
    return render(request, "cabinet/forms/order/orders.html", context)


@login_required()
@permission_required("referral.view_coupon", raise_exception=True)
def coupon_list_view(request: HttpRequest):
    table = CouponsTable(Coupon.objects.all())

    RequestConfig(request, paginate={"per_page": 25}).configure(table)
    export_format = request.GET.get("_export", None)
    if TableExport.is_valid_format(export_format):
        exporter = TableExport(export_format, table)
        return exporter.response("coupons.{}".format(export_format))

    context = {"table": table}
    return render(request, "cabinet/forms/coupon/coupon_list.html", context)


@login_required()
def coupon_list_driver_view(request: HttpRequest):
    """
    Отображает купоны водителя
    """
    table = CouponsDriverTable(request.user.coupons.all())

    RequestConfig(request, paginate={"per_page": 25}).configure(table)

    context = {
        "table": table,
        "header": "Список ваших купонов",
        "breadcrumb_item1": "Меню водителя",
        "breadcrumb_item2": "Купоны",
        "disable_export": True,
        "disable_create": True,
    }
    return render(request, "cabinet/layout/list.html", context)


@login_required()
def apply_coupon_view(request, pk: int):
    """
    Применяет купон
    """
    coupon = get_object_or_404(request.user.coupons.all(), pk=pk)
    is_success = apply_coupon(request.user, coupon)
    if is_success:
        messages.success(request, "Купон успешно применён!")
    else:
        messages.warning(request, "Не удалось применить купон!")
    return redirect("cabinet:coupon_list_driver")


@login_required()
@permission_required("referral.add_coupon", raise_exception=True)
def coupon_create_view(request: HttpRequest):
    """
    Вьюшка для создания новых купонов
    """

    if request.method == "POST":
        form = CreateCouponForm(request.POST)
        if form.is_valid():
            new_coupon: Coupon = form.save()
            return redirect(new_coupon.get_absolute_url())
    else:
        form = CreateCouponForm()

    context = {"form": form}

    return render(request, "cabinet/forms/coupon/coupon_create.html", context)


@login_required()
@permission_required("referral.change_coupon", raise_exception=True)
def coupon_detail_view(request: HttpRequest, pk):
    """
    Вьюшка для редактирования купона
    """
    coupon = get_object_or_404(Coupon, pk=pk)

    if request.method == "POST":
        if "delete" in request.POST:
            coupon.delete()
            return redirect("cabinet:coupon_list_admin")

        form = CouponForm(request.POST, instance=coupon)
        if form.is_valid():
            form.save()
    else:
        form = CouponForm(instance=coupon)

    context = {"form": form, "coupon": coupon}

    return render(request, "cabinet/forms/coupon/coupon_detail.html", context)


@login_required()
def dashboard_view(request: HttpRequest):
    import datetime

    now = datetime.datetime.now
    start = now()
    user_base_queryset = User.objects.select_related(
        "telegram_data",
        "balance",
        "location",
        "telegram_auth_token",
        "driver",
        "driver__car",
        "driver__car__brand",
    ).prefetch_related(
        "rides",
        "rides__client",
        "rides__client__balance",
        "rides__client__telegram_data",
        "rides__client__location",
        "rides__client__telegram_auth_token",
        "rides__client__driver",
        "rides__address",
        "rides__suitable_drivers",
        "driver__work_days",
    )
    clients = user_base_queryset.clients()
    drivers = user_base_queryset.drivers()
    orders = Order.objects.select_related(
        "client",
        "driver",
        "start_location",
        "end_location",
        "start_driver_location",
        "pull_up_driver_location",
        "address",
        "coupon",
        "review",
    ).finished()
    print("First step loading timedelta: ", datetime.datetime.now() - start)

    clients_data = UserExtendedSerializer(clients, many=True).data
    print("clients_data loading timedelta:", now() - start)
    drivers_data = UserExtendedSerializer(drivers, many=True).data
    print("drivers_data loading timedelta:", now() - start)
    orders_data = OrderDashboardSerializer(orders, many=True).data
    print("orders_data loading timedelta:", now() - start)

    context = {
        "clients_count": clients.count(),
        "drivers_count": drivers.count(),
        "orders_count": orders.count(),
        "clients_data": clients_data,
        "drivers_data": drivers_data,
        "orders_data": orders_data,
    }
    print("Dashboard loading timedelta: ", datetime.datetime.now() - start)
    return render(request, "cabinet/dashboard.html", context)


@login_required()
def admin_settings_view(request: HttpRequest):
    cabinet_settings = CabinetSettings.objects.last()
    dispatcher_settings = DispatcherSettings.objects.last()

    cabinet_form = CabinetSettingsForm(instance=cabinet_settings)
    dispatcher_form = DispatcherSettingsForm(instance=dispatcher_settings)

    if request.method == "POST":

        if "submit__cabinet" in request.POST and request.user.has_perm(
            "cabinet.change_settings"
        ):
            cabinet_form = CabinetSettingsForm(request.POST)
            if cabinet_form.is_valid():
                cabinet_form.save()

        elif "submit__dispatcher" in request.POST and request.user.has_perm(
            "dispatcher.change_settings"
        ):
            dispatcher_form = DispatcherSettingsForm(request.POST)
            if dispatcher_form.is_valid():
                dispatcher_form.save()

    template_name = "cabinet/settings_admin.html"
    context = {"cabinet_form": cabinet_form, "dispatcher_form": dispatcher_form}

    return render(request, template_name, context)


@login_required()
@permission_required("dispatcher.view_city", raise_exception=True)
def city_list_view(request: HttpRequest):
    table = CityTable(City.objects.all())

    RequestConfig(request, paginate={"per_page": 25}).configure(table)

    context = {"table": table}
    return render(request, "cabinet/forms/city/city_list.html", context)


@login_required()
@permission_required("dispatcher.view_city", raise_exception=True)
def city_detail_view(request: HttpRequest, pk: int):
    city = get_object_or_404(
        City.objects.select_related("cost_per_km", "cost_per_baby_chair"), pk=pk
    )
    city_form = CityForm(instance=city)
    cost_per_km_form = CostPerKmForm(instance=city.cost_per_km)
    cost_per_baby_chair_form = CostPerBabyChairForm(instance=city.cost_per_baby_chair)

    if request.method == "POST" and request.user.has_perm("dispatcher.change_city"):
        if "submit" in request.POST:
            city_form = CityForm(request.POST, instance=city)
            if city_form.is_valid():
                city = city_form.save()
                messages.success(
                    request, f"Данные города {city.name!r} успешно обновлены!"
                )
        elif "delete" in request.POST and request.user.has_perm(
            "dispatcher.delete_city"
        ):
            city.delete()
            messages.success(request, "Город удалён!")
            return redirect("cabinet:city_list")
        elif "submit__cost_per_km" in request.POST:
            cost_per_km_form = CostPerKmForm(request.POST, instance=city.cost_per_km)
            if cost_per_km_form.is_valid():
                cost_per_km_form.save()
                messages.success(request, "Стоимость за километр успешно обновлена!")
        elif "submit__cost_per_baby_chair" in request.POST:
            cost_per_baby_chair_form = CostPerBabyChairForm(
                request.POST, instance=city.cost_per_baby_chair
            )
            if cost_per_baby_chair_form.is_valid():
                cost_per_baby_chair_form.save()
                messages.success(request, "Стоимость за дестское кресло обновлена!")

    template_name = "cabinet/forms/city/city_detail.html"
    context = {
        "city": city,
        "city_form": city_form,
        "cost_per_km_form": cost_per_km_form,
        "cost_per_baby_chair_form": cost_per_baby_chair_form,
    }

    return render(request, template_name, context)


@login_required()
@permission_required("dispatcher.add_city", raise_exception=True)
def city_create_view(request: HttpRequest):
    form = CreateCityForm()

    if request.method == "POST":
        form = CreateCityForm(request.POST)
        if form.is_valid():
            cost_per_km = CostPerKm(
                value=form.cleaned_data["cost_per_km"],
                night_allowance=form.cleaned_data["cost_per_km__night_allowance"],
            )
            cost_per_km.save()
            cost_per_baby_chair = CostPerBabyChair(
                value=form.cleaned_data["cost_per_baby_chair"],
                night_allowance=form.cleaned_data[
                    "cost_per_baby_chair__night_allowance"
                ],
            )
            cost_per_baby_chair.save()

            city = form.save(commit=False)
            city.cost_per_km = cost_per_km
            city.cost_per_baby_chair = cost_per_baby_chair
            city.save()
            messages.success(request, "Новый город успешно добавлен!")
            return redirect(city.get_absolute_url())
        else:
            # Если форма не прошла валидацию
            messages.warning(request, "Не удалось добавить новый город")

    template_name = "cabinet/forms/city/city_create.html"
    context = {"form": form}
    return render(request, template_name, context)


@login_required()
@permission_required("referral.change_message", raise_exception=True)
def message_list_view(request: HttpRequest):
    table = MessageTable(Message.objects.all())
    RequestConfig(request, paginate={"per_page": 25}).configure(table)

    context = {
        "table": table,
        "title": "ТаксиБер - Список сообщений",
        "header": "Список сообщений",
        "breadcrumb_item2": "Список сообщений",
        "disable_export": True,
        "create_url": reverse("cabinet:message_create"),
    }
    return render(request, "cabinet/layout/list.html", context)


@login_required()
@permission_required("referral.add_message", raise_exception=True)
def message_create_view(request: HttpRequest):
    form = CreateMessageForm()

    if request.method == "POST":
        form = CreateMessageForm(request.POST, request.FILES)
        if form.is_valid():
            message = form.save()
            messages.success(request, "Сообщение создано!")
            return redirect(message.get_absolute_url())

    context = {
        "form": form,
        "header": form.layout_header,
        "breadcrumb_item2": form.layout_header,
    }

    return render(request, "cabinet/layout/detail.html", context)


@login_required()
@permission_required("referral.change_message", raise_exception=True)
def message_detail_view(request: HttpRequest, pk: int):
    message = get_object_or_404(Message, pk=pk)
    form = MessageForm(instance=message)

    if request.method == "POST":
        if "delete" in request.POST and request.user.has_perm(
            "referral.change_message"
        ):
            message.delete()
            messages.success(request, "Сообщение удалено")
            return redirect("cabinet:message_list")
        form = MessageForm(request.POST, request.FILES, instance=message)
        if form.is_valid():
            form.save()
            messages.success(request, "Сообщение сохранено!")

    context = {
        "form": form,
        "header": form.layout_header,
        "breadcrumb_item2": form.layout_header,
    }

    return render(request, "cabinet/layout/detail.html", context)


@login_required()
@permission_required("referral.view_mailing", raise_exception=True)
def mailing_list_view(request: HttpRequest):
    table = MailingTable(Mailing.objects.all())
    RequestConfig(request, paginate={"per_page": 25}).configure(table)

    context = {
        "table": table,
        "title": "ТаксиБер - Список рассылок",
        "header": "Список рассылок",
        "breadcrumb_item2": "Список рассылок",
        "disable_export": True,
        "create_url": reverse("cabinet:mailing_create"),
    }
    return render(request, "cabinet/layout/list.html", context)


@login_required()
@permission_required("referral.add_mailing", raise_exception=True)
def mailing_create_view(request: HttpRequest):
    form = CreateMailingForm()

    if request.method == "POST":
        form = CreateMailingForm(request.POST, request.FILES)
        if form.is_valid():
            mailing = form.save()
            initialize_mailing(mailing=mailing)
            messages.success(request, f"Рассылка #{mailing.pk} создана!")
            return redirect(mailing.get_absolute_url())

    context = {
        "form": form,
        "header": form.layout_header,
        "breadcrumb_item2": form.layout_header,
    }

    return render(request, "cabinet/layout/detail.html", context)


@login_required()
@permission_required("referral.change_mailing", raise_exception=True)
def mailing_detail_view(request: HttpRequest, pk: int):
    mailing = get_object_or_404(Mailing, pk=pk)
    form = MailingForm(instance=mailing)

    if request.method == "POST":
        if "delete" in request.POST and request.user.has_perm(
            "referral.delete_mailing"
        ):
            mailing.delete()
            messages.success(request, "Рассылка удалена!")
            return redirect("cabinet:mailing_list")

        if "start" in request.POST:
            # Если пользователь нажат начать рассылку
            # создаем новый объект рассылки и убираем дату, т.к. она выставится на нынешнюю
            form = MailingForm(request.POST, request.FILES)
            if form.is_valid():
                mailing = form.save()
                mailing.mailing_date = None
                mailing.save()
                initialize_mailing(mailing)
                messages.success(
                    request, f"Создана новая рассылка #{mailing.pk} и сразу запущена!"
                )
                return redirect(mailing.get_absolute_url())

        else:
            form = MailingForm(request.POST, request.FILES, instance=mailing)
            if form.is_valid():
                mailing = form.save()
                messages.success(request, f"Рассылка #{mailing.pk} успешно обновлена!")

    context = {
        "form": form,
        "header": form.layout_header,
        "breadcrumb_item2": form.layout_header,
    }

    return render(request, "cabinet/layout/detail.html", context)


@login_required()
@permission_required("referral.add_raffle", raise_exception=True)
def raffle_create_view(request: HttpRequest):
    # Создание розыгрыша
    if request.method == "POST":
        form = CreateRaffleForm(request.POST)
        if form.is_valid():
            raffle = form.save(commit=False)
            raffle.winner = (
                User.objects.exclude(telegram_data__isnull=True).order_by("?").first()
            )
            try:
                give_coupon_to_user(raffle.winner, raffle.coupon)
            except:
                pass

            send_mailing_to_bot(
                data={
                    "message": MessageSerializer(raffle.message).data,
                    "telegram_ids": [raffle.winner.telegram_data.chat_id],
                }
            )
            raffle.save()
            return redirect(raffle.get_absolute_url())
    else:
        form = CreateRaffleForm()

    context = {
        "form": form,
        "header": form.layout_header,
        "breadcrumb_item2": form.layout_header,
    }

    return render(request, "cabinet/layout/detail.html", context)


@login_required()
@permission_required("referral.view_raffle", raise_exception=True)
def raffle_detail_view(request: HttpRequest, pk: int):
    # Просмотр розыгрыша
    raffle = get_object_or_404(Raffle, pk=pk)

    context = {"raffle": raffle}

    return render(request, "cabinet/forms/raffle/raffle_detail.html", context)


@login_required()
@permission_required("referral.view_raffle", raise_exception=True)
def raffle_list_view(request: HttpRequest):
    # Просмотр списка розыгрышей
    table = RaffleTable(Raffle.objects.all())
    RequestConfig(request, paginate={"per_page": 25}).configure(table)

    context = {
        "table": table,
        "title": "ТаксиБер - Список розыгрышей",
        "header": "Список розыгрышей",
        "breadcrumb_item2": "Список розыгрышей",
        "disable_export": True,
        "create_url": reverse("cabinet:raffle_create"),
    }
    return render(request, "cabinet/layout/list.html", context)
