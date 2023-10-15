from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from data.buttons import (
    ADD_PHONE_NUMBER,
    CONTACT_DATA,
    DRIVER_CABINET,
    ORDER_A_TAXI,
    REFERRAL_PROGRAM,
)
from data.config import WEB_BOT_URL
from models.cabinet import User
from utils.misc.logging import logger

MAIN_MENU_BUTTONS = (REFERRAL_PROGRAM,)
DRIVER_STATUS = "driver"


async def main_menu_keyboard(user: User) -> ReplyKeyboardMarkup:
    """
    Возвращает клавиатуру главного меню, для клиентов и водителей они разные
    """
    logger.info(f"Запрос на клавиатуру главного меню. Пользователь: {user} {user.telegram_auth_token=}")
    keyboard = ReplyKeyboardMarkup(
        row_width=1, resize_keyboard=True, one_time_keyboard=True
    )
    if user.phone_number:
        keyboard.add(
            KeyboardButton(
                text=ORDER_A_TAXI
            )
        )
    else:
        keyboard.add(KeyboardButton(text=ADD_PHONE_NUMBER))
    buttons = (KeyboardButton(text) for text in MAIN_MENU_BUTTONS)
    keyboard.add(*buttons)

    if user.driver:
        keyboard.add(KeyboardButton(DRIVER_CABINET))
    keyboard.add(KeyboardButton(CONTACT_DATA))
    return keyboard



async def register_keyboard():
    
    keyboard = ReplyKeyboardMarkup(
        row_width=1, resize_keyboard=True, one_time_keyboard=True
    )
    keyboard.add(KeyboardButton("Я клиент"))
    keyboard.add(KeyboardButton("Я водитель"))
    return keyboard