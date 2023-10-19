import datetime
import logging

from cabinet.exceptions import (
    DRIVER_ALREADY_WORKING,
    INSUFFICIENT_FUNDS,
    USER_IS_BLOCKED,
    USER_IS_NOT_DRIVER,
)
from cabinet.models import Settings, User, WorkDriverDay
from cabinet.utils.balance import update_user_balance
from django.utils import timezone
from referral.serializers import MessageSerializer
from referral.tasks import send_mailing_to_bot
from referral.utils.coupon import give_coupon_to_user
from rest_framework.exceptions import ParseError


def check_driver(user: User):
    """
            Проверяет, подходит ли водитель для заказа
    :param user:
    :return:
    """
    if user.is_blocked:
        # Если пользователь заблокирован
        raise ParseError(USER_IS_BLOCKED.code)

    if not user.driver:
        raise ParseError(USER_IS_NOT_DRIVER.code)


def make_driver_active(driver: User):
    """
    Выводит водителя на линию (делает активным) или поднимает ошибки
    """
    settings = Settings.objects.last()

    check_driver(driver)  # raise error if not validate

    if driver.driver.is_active:
        raise ParseError(DRIVER_ALREADY_WORKING.code)

    logging.info(
        f"make_driver_active:\n>>{driver.balance.free_days=}\n>>{driver.balance.bonuses=} | {settings.out_line_cost=}\n>>{driver.balance.money=} | {settings.out_line_cost=}"
    )

    if driver.balance.free_days > 0:
        if driver.balance.free_days == 1:
            # Если это последний бонусный день, то нужно отправить сообщение, что бонусные дни закончены
            message = settings.message_2
            send_mailing_to_bot(
                data={
                    "message": MessageSerializer(message).data,
                    "telegram_ids": [driver.telegram_data.chat_id],
                }
            )

        update_user_balance(user_id=driver.pk, value=-1, field="free_days")
        _make_driver_active(user=driver)
        text = "Списан 1 бонусный день."

    elif driver.balance.bonuses >= settings.out_line_cost:
        # Если достаточно бонусов для оплаты
        update_user_balance(
            user_id=driver.pk, value=-settings.out_line_cost, field="bonuses"
        )
        _make_driver_active(user=driver)
        text = f"Списаны бонусы: {settings.out_line_cost} шт."

    elif driver.balance.money >= settings.out_line_cost:
        # Если достаточно денег на счету для оплаты
        update_user_balance(
            user_id=driver.pk, value=-settings.out_line_cost, field="money"
        )
        _make_driver_active(user=driver)
        text = f"Списаны средства с баланса: {settings.out_line_cost} руб."

    else:
        raise ParseError(INSUFFICIENT_FUNDS.code)

    if driver.driver.work_days.all().count() == 7:
        # Если это 7 рабочий день водителя, то выдаём купон ментору
        give_coupon_to_user(driver.mentor, settings.mentor_coupon_2)

    return text

    # raise ParseError(UNKNOWN_PAYMENT_ERROR.code)


def _make_driver_active(user: User):
    start = timezone.now()
    end = start + datetime.timedelta(hours=24)

    work_day = WorkDriverDay(start_date=start, end_date=end, driver=user.driver)
    work_day.save()
