from os import remove as remove_file

from aiogram.dispatcher import FSMContext
from aiogram import types
from aiogram.dispatcher.filters.builtin import CommandStart
from data.config import ICONS_MEDIA_URL
from data.texts import HELLO_STICKER_ID, START_NEW_USER, START_OLD_USER
from handlers.users.main_menu import main_menu_handler
from loader import bot, core, dp
from keyboards.default.main_menu import main_menu_keyboard, register_keyboard
from states.driver import DriverRegister
from utils.to_format import driver_data_state_to_data_core
from utils.exceptions import UserIsRegistered


@dp.message_handler(CommandStart(), state="*")
async def bot_start(message: types.Message, state=None):
    await message.answer(reply_markup=await register_keyboard(), text="Здравствуйте!, выберите вариант регистрации")


async def parse_start_args(args) -> 'Tuple["mentor", "coupon"]':
    if args.startswith("coupon"):
        return (None, args.replace("coupon_", ""))
    else:
        return (args, None)




@dp.message_handler(text="Я водитель")
async def register_driver(message: types.Message, state="*"):
    user = await core.get_user_by_chat_id(chat_id=message.from_user.id)
    if user:
        await message.answer('вы уже зарегистрированы в качестве водителя')

        await message.answer(reply_markup=await main_menu_keyboard(user=user), text="Главное меню")
    else:
        await message.answer('молодец')
        await state.set_state(DriverRegister.car_brand)
        await message.answer('укажите бренд вашей машины')


@dp.message_handler(state=DriverRegister.car_brand)
async def register_driver(message: types.Message, state="*"):
    await message.answer('молодец')
    await state.update_data(car_brand=message.text)
    await state.set_state(DriverRegister.car_number)
    await message.answer('укажите номер вашей машины')


@dp.message_handler(state=DriverRegister.car_number)
async def register_driver(message: types.Message, state="*"):
    await message.answer('молодец')
    await state.update_data(car_number=message.text)
    await state.set_state(DriverRegister.car_color)
    await message.answer('укажите цвет вашей машины')



@dp.message_handler(state=DriverRegister.car_color)
async def register_driver(message: types.Message, state=FSMContext):
    await message.answer('молодец')
    await state.update_data(car_color=message.text)
    await state.set_state(DriverRegister.phone_number)
    await message.answer('напишите ваш номер телефона в формате 79159999999')


@dp.message_handler(state=DriverRegister.phone_number)
async def register_driver(message: types.Message, state=FSMContext):
    await message.answer('молодец')
    try:
        int(message.text)
        if len(message.text) != 11 or message.text[0:2] != '79':
            await state.set_state(DriverRegister.phone_number)
            await message.answer('не молодец')
        else:

            await state.update_data(phone_number=f'+{message.text}')
            await state.set_state(DriverRegister.baby_chair)
            await message.answer('у вас есть детское кресло? (Да/Нет)')
    except:

        await state.set_state(DriverRegister.phone_number)
        await message.answer('не молодец')




@dp.message_handler(state=DriverRegister.baby_chair)
async def register_driver(message: types.Message, state=FSMContext):
    await message.answer('молодец')
    await state.update_data(baby_chair=message.text)
    await state.set_state(DriverRegister.photo)

@dp.message_handler(state=DriverRegister.photo, content_types=types.ContentType.ANY)
async def register_driver(message: types.Message, state=FSMContext):
    data = await driver_data_state_to_data_core(await state.get_data())
    data['chat_id'] = message.from_user.id
    try:
        status = await core.create_driver(
            user_data=data,
        )
        if status:
            await message.answer(f"Вы успешно зарегистрировались! {status}")
            await state.finish()
        else:
            await message.answer(f"Регистрация не удалось. Попробуйте еще раз")
            await state.finish()
    except:
        await state.finish()




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