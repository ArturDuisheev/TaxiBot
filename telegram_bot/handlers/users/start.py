import re
from os import remove as remove_file

from aiogram.utils.callback_data import CallbackData

from data.texts import OPEN_MAIN_MENU
from aiogram.dispatcher import FSMContext
from aiogram import types
from aiogram.dispatcher.filters.builtin import CommandStart
from data.config import ICONS_MEDIA_URL, ADMINS
from data.texts import HELLO_STICKER_ID, START_NEW_USER, START_OLD_USER
from handlers.users.main_menu import main_menu_handler
from loader import bot, core, dp
from keyboards.default.main_menu import main_menu_keyboard, register_keyboard
from states.driver import DriverRegister
from utils.to_format import driver_data_state_to_data_core
from utils.exceptions import UserIsRegistered
from states.help import HelpState

@dp.message_handler(CommandStart(), state="*")
async def bot_start(message: types.Message, state=FSMContext):
    # Запрос на регистрацию пользователя
    try:
        user = await core.get_user_by_chat_id(chat_id=message.from_user.id)
    except:
        user = None
    if user:
        await message.answer('вы уже зарегистрированы')
        keyboard = await main_menu_keyboard(user=user)
        await message.answer(reply_markup=keyboard, text=OPEN_MAIN_MENU)
    else:
        mentor, coupon = await parse_start_args(message.get_args())
        if coupon:
            coupon = await core.pick_coupon(
                chat_id=message.from_user.id, coupon_code=coupon
            )
            await message.answer(f"Купон применен! {coupon.name}")
            return
        if state:
            await state.finish()
        photos = await bot.get_user_profile_photos(user_id=message.from_user.id, limit=1)
        user_photo = (
            await photos.photos[0][-1].download(ICONS_MEDIA_URL, make_dirs=True)
            if len(photos.photos) > 0
            else None
        )
        try:
            user = await core.register_user(
                user_data=message.from_user,
                user_photo_path=user_photo.name if user_photo else None,
                mentor_chat_id=mentor,
            )
        except UserIsRegistered:
            user = None
        if user:
            text = START_NEW_USER.format(name=message.from_user.first_name)
        else:
            text = START_OLD_USER.format(name=message.from_user.first_name)
        await message.answer_sticker(HELLO_STICKER_ID)

        await message.answer('подтвердите ознакомление с офертой (Подтверждаю, Нет)',
                             reply_markup=types.ReplyKeyboardMarkup([[
                                 types.KeyboardButton("подтверждаю"),
                                 types.KeyboardButton("нет")
                             ]]))
        await message.reply_document(open("data/static/oferta.doc", 'rb'))
        await state.set_state(DriverRegister.oferta)

        if user_photo:
            remove_file(user_photo.name)
    

@dp.message_handler(state=DriverRegister.oferta)
async def register(message: types.Message, state=FSMContext):
    if message.text.lower() != 'подтверждаю' and message.text.lower() != "да":
        await message.answer('Без подтверждения ознакомления с офертой, мы не можем вас зарегистрировать')
        await state.set_state(DriverRegister.oferta)
        return
    await state.finish()
    user = await core.get_user_by_chat_id(chat_id=message.from_user.id)
    keyboard = await main_menu_keyboard(user=user)
    keyboard.add(types.KeyboardButton(
            text="Я водитель"
        ))
    await message.answer(reply_markup=keyboard, text=OPEN_MAIN_MENU)
    

async def parse_start_args(args) -> 'Tuple["mentor", "coupon"]':
    if args.startswith("coupon"):
        return (None, args.replace("coupon_", ""))
    else:
        return (args, None)




@dp.message_handler(text="Я водитель")
async def register_driver(message: types.Message, state="*"):
    try:
        user = await core.get_user_by_chat_id(chat_id=message.from_user.id)
        is_driver = user.driver
    except:
        user = None
        is_driver = None
    print(is_driver, 123213)
    if is_driver:
        await message.answer('вы уже зарегистрированы в качестве водителя')
    else:
        await state.set_state(DriverRegister.car_brand)
        await message.answer('укажите бренд вашей машины')


@dp.message_handler(state=DriverRegister.car_brand)
async def register_driver(message: types.Message, state="*"):
    await state.update_data(car_brand=message.text)
    await state.set_state(DriverRegister.car_number)
    await message.answer('укажите номер вашей машины')


@dp.message_handler(state=DriverRegister.car_number)
async def register_driver(message: types.Message, state="*"):
    if not re.match(r"[АВЕКМНОРСТУХ]\d{3}(?<!000)[АВЕКМНОРСТУХ]{2}\d{2,3}", message.text.upper()):
        await message.answer("номер машины не валиден, пример х777хх77")
    else:
        await state.update_data(car_number=message.text)
        await state.set_state(DriverRegister.car_color)
        await message.answer('укажите цвет вашей машины')



@dp.message_handler(state=DriverRegister.car_color)
async def register_driver(message: types.Message, state=FSMContext):
    await state.update_data(car_color=message.text)
    await state.set_state(DriverRegister.phone_number)
    await message.answer('напишите ваш номер телефона в формате 79159999999')


@dp.message_handler(state=DriverRegister.phone_number)
async def register_driver(message: types.Message, state=FSMContext):
    try:
        int(message.text)
        if len(message.text) != 11 or message.text[0:2] != '79':
            await state.set_state(DriverRegister.phone_number)
            await message.answer('неверный формат вашего номера телефона, укажите его еще раз')
        else:

            await state.update_data(phone_number=f'+{message.text}')
            await state.set_state(DriverRegister.baby_chair)
            await message.answer('у вас есть детское кресло? (Да/Нет)')
    except:

        await state.set_state(DriverRegister.phone_number)
        await message.answer('неверный формат вашего номера телефона, укажите его еще раз')




@dp.message_handler(state=DriverRegister.baby_chair)
async def register_driver(message: types.Message, state=FSMContext):
    await state.update_data(baby_chair=message.text)
    await message.answer('подтвердите ознакомление с офертой (Подтверждаю, Нет)',
                             reply_markup=types.ReplyKeyboardMarkup([[
                                 types.KeyboardButton("подтверждаю"),
                                 types.KeyboardButton("нет")
                             ]]))
    await message.reply_document(open("data/static/oferta.doc", 'rb'))
    await state.set_state(DriverRegister.photo)

@dp.message_handler(state=DriverRegister.photo)
async def register_driver(message: types.Message, state=FSMContext):
    if message.text.lower() != 'подтверждаю' and message.text.lower() != "да":
        await message.answer('Без подтверждения ознакомления с офертой, мы не можем вас зарегистрировать')
        await state.set_state(DriverRegister.photo)
        return
    data = await driver_data_state_to_data_core(await state.get_data())
    await state.finish()
    data['chat_id'] = message.from_user.id
    status = await core.create_driver(
        user_data=data,
    )
    if status:
        user = await core.get_user_by_chat_id(chat_id=message.from_user.id)
        await message.answer(f"Вы успешно зарегистрировались!", reply_markup=await main_menu_keyboard(user=user))

    else:
        await message.answer(f"Регистрация не удалось. Попробуйте еще раз")



@dp.message_handler(text="Я пользователь")
async def register_user(message: types.Message, state=None):
    # Запрос на регистрацию пользователя
    user = await core.get_user_by_chat_id(chat_id=message.from_user.id)
    if user:
        await message.answer('вы уже зарегистрированы')
    else:
        mentor, coupon = await parse_start_args(message.get_args())
        if coupon:
            coupon = await core.pick_coupon(
                chat_id=message.from_user.id, coupon_code=coupon
            )
            await message.answer(f"Купон применен! {coupon.name}")
            return
        if state:
            await state.finish()
        photos = await bot.get_user_profile_photos(user_id=message.from_user.id, limit=1)
        user_photo = (
            await photos.photos[0][-1].download(ICONS_MEDIA_URL, make_dirs=True)
            if len(photos.photos) > 0
            else None
        )
        try:
            user = await core.register_user(
                user_data=message.from_user,
                user_photo_path=user_photo.name if user_photo else None,
                mentor_chat_id=mentor,
            )
        except UserIsRegistered:
            user = None
        if user:
            text = START_NEW_USER.format(name=message.from_user.first_name)
        else:
            text = START_OLD_USER.format(name=message.from_user.first_name)
        await message.answer_sticker(HELLO_STICKER_ID)
        await main_menu_handler(
            message, state, pre_text=text + "\n", user=user, base_text=""
        )

        if user_photo:
            remove_file(user_photo.name)


@dp.callback_query_handler(lambda x: x.data == "cancel_helps")
async def cancel_help(callback: types.CallbackQuery, state: FSMContext):
    await state.finish()
    await callback.message.answer("Отменено")
    await main_menu_handler("", chat_id=callback.from_user.id)

@dp.message_handler(text="Помощь")
async def help(message: types.Message, state: FSMContext):
    await state.set_state(HelpState.text)
    await message.answer("Напишите свою проблему и мы обязательно вам поможем. "
                         "Если вы нажали кнопку случайно, напишите слово, Отменить")


@dp.message_handler(state=HelpState.text)
async def text_help(message: types.Message, state: FSMContext):
    if message.text.lower() == "отменить":
        await message.answer("Отменено")
        await state.finish()
        return
    for admin in ADMINS:
        await bot.send_message(admin, f"Пользователь: @{message.from_user.username} "
                                      f"написал в поддержку с сообщением - {message.text}")
    await message.answer("Ваше сообщение было отправлено, скоро с вами свяжутся")
    await state.finish()
