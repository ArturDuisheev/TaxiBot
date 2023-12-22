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


@dp.callback_query_handler(lambda x: x.data == "add_balance")
@authenticate(fields=["driver"], extended=True)
async def payment_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(DriverPayment.price)
    await callback.message.answer("Введите сумму пополнения")

@dp.message_handler(state=DriverPayment.price)
async def payment_complete(message: types.Message, state: FSMContext):
    try:
        price = int(message.text)
        if price < 100:
            await message.answer("Введенной число меньше 100")
            return
    except:
        await state.set_state(DriverPayment.price)
        await message.answer("Введенное сообщение, не число. Введите сумму пополнения заново")
        await state.finish()
        return
    # Для теста товары будут в этой функции, на проде необходим отдельный файл
    PRICE = [types.LabeledPrice(label="Оплата за сервис", amount=price * 100)]
    await bot.send_invoice(chat_id=message.from_user.id, title="Оплата",
                           description="Оплата за сервис", provider_token=PAY_TOKEN,
                           currency='rub', is_flexible=False,
                           prices=PRICE, start_parameter='1',
                           payload='1',
                           need_shipping_address=False
                           )
    await state.finish()


@dp.pre_checkout_query_handler(lambda x: True)
async def pre_checkout_query(pre_checkout_query: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message_handler(content_types=types.ContentType.SUCCESSFUL_PAYMENT)
async def successful_payment(message: types.Message):
    
    user = await core.get_user_by_chat_id(message.from_user.id)
    await message.answer("Обрабатываем платеж")
    await core.update_user_balance(user_id=user.id, value=message.successful_payment.total_amount / 100)
    await message.answer_sticker(HELLO_STICKER_ID)
    
    await message.answer("Платеж прошел успешно!")
    


@dp.message_handler(text=ADD_PHONE_NUMBER)
async def phone_number_handler(message: types.Message):
    await UpdatePhoneNumber.is_active.set()
    await message.answer(
        SEND_PHONE, reply_markup=await request_data_keyboard(buttons=["phone"])
    )
