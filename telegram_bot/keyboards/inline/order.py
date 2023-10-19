from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, KeyboardButton
from aiogram.utils.callback_data import CallbackData
from data.buttons import (
    ACCEPT_ORDER as ACCEPT_ORDER_BUTTON,
    WRITE_ADDRESS,
    REPEAT_ORDER,
)
from data.buttons import ADD_COMMENT, BACK, CANCEL_ORDER, CLIENT_GOT_INTO_CAR
from data.buttons import DECLINE_ORDER as DECLINE_ORDER_BUTTON
from data.buttons import EXIT, FINISH_RIDE, I_DROVE_UP, ORDER_A_TAXI, RATE_RIDE
from models.dispatcher import (
    ACCEPTED,
    DRIVER_IS_WAITING,
    ORDER_IS_CREATED,
    RIDE_IS_FINISHED,
    RIDE_IS_STARTED,
    WAIT_TO_ACCEPT,
    Order,
)
from data.config import WEB_BOT_URL

CB_ORDER_ID, CB_ACTION = ("order_id", "action")
ACCEPT_ORDER, DECLINE_ORDER = ("accept", "decline")
RECREATE_ORDER = "recreate_order"
CREATE_ORDER_REVISION = "create_order_revision"
CB_STATUS = "status"
CB_STARS = "stars"
IS_DRIVER = "is_driver"
GIVE_REVIEW = "give_review"
ORDER_ACTIONS = (ORDER_A_TAXI, ADD_COMMENT)

client_cb = CallbackData("order_cb", CB_ORDER_ID, CB_ACTION)
driver_cb = CallbackData("driver_cb", CB_ORDER_ID, CB_ACTION)
update_status_cb = CallbackData("update_order_status", CB_ORDER_ID, CB_STATUS)
review_cb = CallbackData("review_cb", CB_ORDER_ID, CB_STARS, IS_DRIVER)


async def order_keyboard(order: Order) -> InlineKeyboardMarkup:
    """
    Возвращает инлайн клавиатуру при подтверждении заказа
    """
    print(f"Запрос клавиатуры для заказа со статусом: {order.status}")
    keyboard = InlineKeyboardMarkup(row_width=1)
    cancel_order_button = InlineKeyboardButton(
        text=CANCEL_ORDER,
        callback_data=client_cb.new(order_id=order.id, action=CANCEL_ORDER),
    )
    if order.status == ORDER_IS_CREATED:
        buttons = (
            InlineKeyboardButton(
                text=text, callback_data=client_cb.new(order_id=order.id, action=text)
            )
            for text in ORDER_ACTIONS
        )

        keyboard.add(*buttons)

    elif order.status == RIDE_IS_FINISHED:
        keyboard.add(
            InlineKeyboardButton(
                text=RATE_RIDE,
                callback_data=client_cb.new(order_id=order.id, action=GIVE_REVIEW),
            )
        )

    else:
        keyboard.add(KeyboardButton("🗺 Открыть заказ", web_app=WebAppInfo(url=WEB_BOT_URL + "?telegram_auth_token=" + order.client.telegram_auth_token)))

    print(f"{order.status=}, {RIDE_IS_STARTED=} {RIDE_IS_FINISHED=}")
    if order.status not in [RIDE_IS_STARTED, RIDE_IS_FINISHED]:
        keyboard.add(cancel_order_button)

    return keyboard


async def order_driver_keyboard(order: Order) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(row_width=1)

    if order.status == WAIT_TO_ACCEPT:
        # Если заказ в статусе ожидания принятия от водителей
        keyboard.add(
            InlineKeyboardButton(
                text=ACCEPT_ORDER_BUTTON,
                callback_data=driver_cb.new(order.id, ACCEPT_ORDER),
            )
        )
        keyboard.add(
            InlineKeyboardButton(
                text=DECLINE_ORDER_BUTTON,
                callback_data=driver_cb.new(order.id, DECLINE_ORDER),
            )
        )

    elif order.status == ACCEPTED:
        # Если заказ уже принят водителем
        keyboard.add(
            InlineKeyboardButton(
                text=I_DROVE_UP,
                callback_data=update_status_cb.new(order.id, DRIVER_IS_WAITING),
            )
        )
    elif order.status == DRIVER_IS_WAITING:
        # Когда водитель подъехал и ожидает клиента
        keyboard.add(
            InlineKeyboardButton(
                text=CLIENT_GOT_INTO_CAR,
                callback_data=update_status_cb.new(order.id, RIDE_IS_STARTED),
            )
        )
    elif order.status == RIDE_IS_STARTED:
        # Когда клиент сел в машину и водитель начал поездку
        keyboard.add(
            InlineKeyboardButton(
                text=FINISH_RIDE,
                callback_data=update_status_cb.new(order.id, RIDE_IS_FINISHED),
            )
        )
    elif order.status == RIDE_IS_FINISHED:
        # Когда поездка завершена
        keyboard.add(
            InlineKeyboardButton(
                text=RATE_RIDE,
                callback_data=driver_cb.new(order_id=order.id, action=GIVE_REVIEW),
            )
        )

    return keyboard


async def cancel_order_driver_keyboard(order: Order) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(row_width=1)
    cancel_order_button = InlineKeyboardButton(
        text=CANCEL_ORDER, callback_data=driver_cb.new(order.id, CANCEL_ORDER)
    )
    keyboard.add(cancel_order_button)
    return keyboard


async def review_keyboard(order_id, is_driver=False) -> InlineKeyboardMarkup:
    """
    Возвращает клавиатуру для оценки заказа
    """

    keyboard = InlineKeyboardMarkup(row_width=1)
    buttons = (
        InlineKeyboardButton(
            text="⭐️" * i, callback_data=review_cb.new(order_id=order_id, stars=i, is_driver=is_driver)
        )
        for i in reversed(range(1, 6))
    )
    keyboard.add(*buttons)
    return keyboard
    pass


async def address_write_inline_keyboard(exit=False, back=False, switch_text="") -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(text=WRITE_ADDRESS, switch_inline_query_current_chat=switch_text)
    )

    if back:
        keyboard.add(InlineKeyboardButton(text=BACK, callback_data=BACK))
    if exit:
        keyboard.add(InlineKeyboardButton(text=EXIT, callback_data=EXIT))

    return keyboard


async def revision_order_keyboard(order_id) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(
            text=REPEAT_ORDER, callback_data=client_cb.new(order_id, RECREATE_ORDER)
        )
    )
    return keyboard


async def create_order_revision_keyboard(order_id) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(
            text="🛎 Уведомить, если найдутся машины 🛎",
            callback_data=client_cb.new(order_id, CREATE_ORDER_REVISION),
        )
    )
    return keyboard
