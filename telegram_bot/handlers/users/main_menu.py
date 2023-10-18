from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.builtin import Command
from data.buttons import ADD_PHONE_NUMBER, CONTACT_DATA
from data.texts import HELLO_STICKER_ID, OPEN_MAIN_MENU, SEND_PHONE, WRONG_PHONE
from keyboards.default import main_menu_keyboard
from keyboards.default.request_data import request_data_keyboard
from loader import bot, core, dp
from middlewares.authentication import authenticate
from states.main_menu import UpdatePhoneNumber
from states.driver import DriverPayment
from utils.phone_numbers import validate_phone_number
from data.config import PAY_TOKEN


@dp.message_handler(Command("menu"), state="*")
async def main_menu_handler(
    message: types.Message,
    state: FSMContext = None,
    pre_text: str = "",
    post_text: str = "",
    base_text: str = ...,
    user=None,
    chat_id: int = None,
    is_start=False
):
    if state:
        await state.finish()

    chat_id = chat_id or message.from_user.id
    user = await core.get_user_by_chat_id(chat_id=chat_id, extended=True)
    if is_start:
        keyboard = await main_menu_keyboard(user=user)
        keyboard.add(types.KeyboardButton(
                text="Я водитель"
            ))
    else:
        keyboard = await main_menu_keyboard(user=user)

    text = base_text if base_text != ... else OPEN_MAIN_MENU
    await bot.send_message(
        chat_id,
        pre_text + text + post_text,
        reply_markup=keyboard,
    )



@dp.message_handler(text=CONTACT_DATA)
async def phone_number_handler(message: types.Message):
    await message.reply_document(open("data/static/contact_data.doc", 'rb'))

@dp.message_handler(
    state=UpdatePhoneNumber.is_active, content_types=types.ContentTypes.ANY
)
@authenticate()
async def update_phone_number_handler(message: types.Message, state: FSMContext):
    contact = message.contact
    if contact:
        phone_number = validate_phone_number(contact.phone_number)
    else:
        phone_number = validate_phone_number(message.text)

    if not phone_number:
        await message.answer(
            WRONG_PHONE, reply_markup=await request_data_keyboard(buttons=["phone"])
        )
        return

    await core.update_user(user_id=message.user.id, phone_number=phone_number)
    await main_menu_handler(
        message, state, pre_text="Номер телефона успешно обновлён!\n\n"
    )
