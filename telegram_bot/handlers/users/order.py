import logging
from asyncio import sleep

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.builtin import Command
from aiogram.types import (
    InlineQueryResultArticle,
    InlineQueryResultLocation,
    InputLocationMessageContent,
)
from data import texts as t
from data.buttons import BACK, EXIT, NO, WRITE_ADDRESS, YES
from data.texts import PLEASE_CLICK_YES_OR_NO, PRE_ORDER_TEXT
from handlers.users.main_menu import main_menu_handler
from keyboards.default import generator as keyboard_generator
from keyboards.default import request_data_keyboard
from keyboards.inline import order_keyboard, pick_coupons_keyboard
from keyboards.inline.order import (
    ADD_COMMENT,
    CANCEL_ORDER,
    CB_ORDER_ID,
    CB_STARS,
    CREATE_ORDER_REVISION,
    GIVE_REVIEW,
    IS_DRIVER,
    ORDER_A_TAXI,
    RECREATE_ORDER,
    address_write_inline_keyboard,
    client_cb,
    create_order_revision_keyboard,
    order_driver_keyboard,
    review_cb,
    review_keyboard,
)
from keyboards.inline.pick_coupons import cb as pick_coupons_cb
from loader import bot, core, dp, location_storage
from middlewares.authentication import authenticate
from models.dispatcher import (
    ORDER_CANCELED_BY_CLIENT,
    PAYMENT_METHOD_CHOICES,
    WAIT_TO_ACCEPT,
    Order,
    OrderReview,
    initialize_location,
)
from states.order import (
    ORDER_STATE,
    PICK_END_LOCATION,
    PICK_START_LOCATION,
    OrderReviewState,
    OrderSity,
    OrderState,
)
from utils.checks import location_check
from utils.exceptions import NoActionFound, OrderError
from utils.geolocator import get_sity_from_location, get_autocompletion_inline_results
from utils.mailing import message_to_user_list
from utils.phone_numbers import validate_phone_number


async def set_step(chat_id: int, step_name: str, data=None):
    if step_name == "pick_start_location":
        await bot.send_message(
            chat_id=chat_id,
            text=t.SEND_LOCATION_A,
            reply_markup=await request_data_keyboard(buttons=["location", "address"]),
        )
        await OrderState.pick_start_location.set()

    elif step_name == "pick_end_location":
        # await bot.send_message(chat_id=chat_id, text=t.SEND_LOCATION_B, reply_markup= await request_data_keyboard(buttons=['address']))
        await OrderState.pick_end_location.set()
        await bot.send_message(
            chat_id=chat_id,
            text=t.SEND_LOCATION_B,
            reply_markup=await address_write_inline_keyboard(exit=True, switch_text=data),
        )

    elif step_name == "pick_baby_chair":
        await bot.send_message(
            chat_id=chat_id,
            text=t.ARE_YOU_NEED_BABY_CHAIR,
            reply_markup=await keyboard_generator(YES, NO, EXIT),
        )
        await OrderState.pick_baby_chair.set()

    elif step_name == "pick_coupon":
        state = dp.current_state()
        data = await state.get_data()
        user = data.get("client")
        # Если у пользователя нет купонов, то шаг выборы купона пропускается
        coupons = user.get_ride_discount_coupons()

        if not coupons:
            # Сообщение о том, что купоны отсутствуют, временно убрано
            # await bot.send_message(chat_id=chat_id,
            #                        text=t.YOU_DONT_HAVE_COUPONS)
            return await set_step(chat_id=chat_id, step_name="pick_payment_method")

        await bot.send_message(
            chat_id=chat_id,
            text=t.PICK_PROMOCODE,
            reply_markup=await pick_coupons_keyboard(coupons=coupons),
        )
        await OrderState.pick_coupon.set()

    elif step_name == "pick_payment_method":
        await bot.send_message(
            chat_id=chat_id,
            text=t.PICK_PAYMENT_METHOD,
            reply_markup=await keyboard_generator(*PAYMENT_METHOD_CHOICES, EXIT),
        )
        await OrderState.pick_payment_method.set()

    elif step_name == "pick_phone_number":
        await bot.send_message(
            chat_id=chat_id,
            text=t.SEND_PHONE,
            reply_markup=await request_data_keyboard(buttons=["phone"]),
        )
        await OrderState.pick_phone_number.set()

    elif step_name == "pick_price":
        await bot.send_message(chat_id=chat_id, text=PRE_ORDER_TEXT)
        state = dp.current_state()
        data = await state.get_data()
        order = await core.create_order(data)
        await send_preorder(chat_id, order, state=state)

    else:
        print("Ошибка! Передан неверный шаг при принятии заказа.")


@dp.async_task
async def send_preorder(chat_id, order, state=None):
    # await OrderState.pick_price.set()
    await OrderState.order_in_progress.set()
    if not state:
        state = dp.current_state()
    if not order.suitable_drivers:
        # Если не удалось найти водителей по-близости
        await bot.send_message(
            chat_id,
            t.NO_SUITABLE_DRIVERS,
            reply_markup=await create_order_revision_keyboard(order_id=order.id),
        )
        return await main_menu_handler(
            message=None, state=state, user=order.client, chat_id=chat_id
        )

    # msg = await bot.send_location(
    #     chat_id=chat_id,
    #     latitude=order.start_location.latitude,
    #     longitude=order.start_location.longitude,
    # )

    # Обновляем статус заказа
    order: Order = await core.update_order_status(
        order_id=order.id, status=WAIT_TO_ACCEPT
    )
    msg = await bot.send_message(
        chat_id,
        t.I_SEND_MESSAGE_WHEN_DRIVER_ACCEPT_ORDER % order.as_text(),
        reply_markup=await order_keyboard(order=order),
    )
    await state.update_data(order=order, order_message_id=msg.message_id)

    text = t.NEW_ORDER_BASE_TEXT + "\n\n" + order.as_text()

    if order.is_need_baby_chair:
        text += f"\n\n⚠️ Нужно детское кресло!"

    await message_to_user_list(
        user_list=[user.telegram_data.chat_id for user in order.suitable_drivers],
        text=text,
        reply_markup=await order_driver_keyboard(order=order),
    )

    order_id = order.id
    # Если, через 5 минут водители не найдены, то уведомляет об этом
    await sleep(300)
    data = await state.get_data()
    order: Order = data.get("order")
    if order and order.id == order_id:
        if order.status == WAIT_TO_ACCEPT:
            await bot.send_message(
                chat_id,
                "Прошло 5 минут, никто из водителей не принял заказ. "
                "Вы можете подождать еще, возможно кто-то завершает заказ, или вы можете отменить заказ."
            )


@dp.message_handler(text=ORDER_A_TAXI)
@authenticate()
async def order_taxi_handler(message):
    # Пробуем открыть заказ, не отправляем сообщение о том, что заказ не найден
    try:
        order = await open_order(
            message,
            send_no_order_message=False,
            pre_text="У вас уже есть активный заказ. Сначала завершите его!\n\n",
        )
    except OrderError:
        order = None
    # Если заказ найден, то выходим из функции
    if order:
        await location_storage.set_data(key=f'user_order_{order.id}', data=message.from_user.id)
        return

    # Если заказ не найден, то начинаем оформление заказа
    await set_step(chat_id=message.from_user.id, step_name="pick_start_location")
    # State в данный момент
    state = dp.current_state()
    # Обновляем, ставим пользователя как клиента, чтобы избежать лишних запросов в будущем
    await state.update_data(client=message.user)


@dp.message_handler(
    state=[OrderState.pick_start_location, OrderState.pick_end_location],
    text=WRITE_ADDRESS,
)
async def pick_start_location_text_handler(message: types.Message, state: FSMContext):

    await message.answer(
        f"Чтобы ввести адрес вручную нажмите на кнопку ниже. Если вы передумали, то нажмите «{BACK}» чтобы вернуться назад.",
        reply_markup=await address_write_inline_keyboard(back=True),
    )


@dp.message_handler(
    state=OrderState.pick_start_location, content_types=types.ContentTypes.ANY
)
@location_check  # Валидация сообщения на наличие геопозиции
async def pick_start_location_handler(message: types.Message, state):
    """
    Принимает геопозицию точки отправления, проверяет на тип сообщения,
    сохраняет в хранилище объект Location
    """
    
    sity = await get_sity_from_location(location=message.location)
    await message.answer("Адрес отправки получен!")
    await state.update_data(start_location=initialize_location(message.location))

    print("Start location: ", message.location)

    await set_step(message.from_user.id, "pick_end_location", sity)


@dp.message_handler(
    state=OrderState.pick_end_location, content_types=types.ContentTypes.ANY
)
# @location_check
async def pick_end_location_handler(message: types.Message, state):
    """
    Принимает геопозицию точки прибытия
    """
    if not message.location:
        return await message.answer(
            f"Нажмите кнопку «{WRITE_ADDRESS}» выше, и начните вводить, так я смогу найти вам нужный адрес!"
        )
    print("End location: ", message.location)
    await message.answer("Адрес прибытия получен!")
    await state.update_data(end_location=initialize_location(message.location))
    await set_step(chat_id=message.from_user.id, step_name="pick_baby_chair")


@dp.message_handler(
    state=OrderState.pick_baby_chair, content_types=types.ContentTypes.ANY
)
async def pick_baby_chair_handler(message, state):
    """
    Узнает нужно ли детское кресло
    """
    if message.text == YES:
        result = True
    elif message.text == NO:
        result = False
    else:
        await message.answer(PLEASE_CLICK_YES_OR_NO % (YES, NO))
        return

    await state.update_data(is_need_baby_chair=result)

    await set_step(chat_id=message.from_user.id, step_name="pick_coupon")


@dp.callback_query_handler(pick_coupons_cb.filter(), state=OrderState.pick_coupon)
async def pick_coupon_inline_handler(
        call: types.CallbackQuery, state, callback_data: dict
):
    coupon_pk = callback_data.get("pk")
    if coupon_pk == "-":
        await call.message.answer(t.PICK_COUPON_SKIPED)

    else:
        await state.update_data(coupon_pk=coupon_pk)
        await call.message.answer(t.COUPON_APPLIED)

    await set_step(chat_id=call.from_user.id, step_name="pick_payment_method")


@dp.message_handler(
    state=OrderState.pick_payment_method, content_types=types.ContentTypes.ANY
)
async def pick_payment_method(message, state):
    if message.text not in PAYMENT_METHOD_CHOICES:
        await message.answer(
            t.WRONG_PAYMENT_METHOD,
            reply_markup=await keyboard_generator(*PAYMENT_METHOD_CHOICES),
        )
        return

    await state.update_data(payment_method=PAYMENT_METHOD_CHOICES.get(message.text))
    await set_step(chat_id=message.from_user.id, step_name="pick_phone_number")


@dp.message_handler(
    state=OrderState.pick_phone_number, content_types=types.ContentTypes.ANY
)
async def pick_phone_number(message, state):
    contact = message.contact
    if contact:
        phone_number = validate_phone_number(contact.phone_number)
    else:
        phone_number = validate_phone_number(message.text)

    if not phone_number:
        await message.answer(
            t.WRONG_PHONE, reply_markup=await request_data_keyboard(buttons=["phone"])
        )
        return

    await state.update_data(client_phone=phone_number)
    await set_step(chat_id=message.from_user.id, step_name="pick_price")


@dp.inline_handler(state=[OrderState.pick_start_location, OrderState.pick_end_location])
async def address_inline_handler(inline_query: types.InlineQuery, state: FSMContext):
    """
    Автозаполняет адреса
    """
    print('queiry_comm')
    try:
        results = await get_autocompletion_inline_results(inline_query.query)
    except Exception as E:
        results = []
        logging.warning(E.args)
    print('queiry_comm')
    cache_time = 1000
    await bot.answer_inline_query(
        inline_query.id, results=results, cache_time=cache_time
    )


@dp.callback_query_handler(
    text=BACK, state=[OrderState.pick_start_location, OrderState.pick_end_location]
)
async def exit_from_write_address_handler(
        callback: types.CallbackQuery, state: FSMContext
):
    """
    Выход из режима ввода адреса
    """
    state_name = await state.get_state()

    if state_name == ORDER_STATE + ":" + PICK_START_LOCATION:
        await set_step(callback.from_user.id, "pick_start_location")
    elif state_name == ORDER_STATE + ":" + PICK_END_LOCATION:
        await set_step(callback.from_user.id, "pick_end_location")

    await callback.message.delete()


@dp.callback_query_handler(client_cb.filter(), state="*")
@dp.async_task
async def pick_accept_order_action(
        call: types.CallbackQuery, state: FSMContext, callback_data: dict
):
    action = callback_data.get("action")
    print(callback_data, 'callback')
    if action == CANCEL_ORDER:
        order: Order = await get_order(client_chat_id=call.from_user.id, state=state)
        await cancel_order(order)
        await call.message.edit_reply_markup(reply_markup=None)

    elif action == GIVE_REVIEW:
        # Если пользователь нажал "Оценить поездку"
        # TODO: Сделать систему принятия оценки за поездку
        await OrderReviewState.pick_stars.set()
        print(f"{callback_data=}")
        await call.message.edit_reply_markup(reply_markup=None)
        await call.message.reply(
            "Спасибо, что оставляете оценку, это поможет нам улучшить сервис! Выберите количество звёзд от 1 до 5.",
            reply_markup=await review_keyboard(order_id=callback_data[CB_ORDER_ID]),
        )


    elif action == CREATE_ORDER_REVISION:
        await call.message.edit_reply_markup(reply_markup=None)
        order_id = int(callback_data[CB_ORDER_ID])
        await core.create_order_revision(order_id)
        return await call.answer(
            "Хорошо! Я уведомлю вас, если найду свободных водителей в течение 10 минут.",
            show_alert=True,
        )

    elif action == RECREATE_ORDER:
        await call.message.delete()
        order_id = int(callback_data.get(CB_ORDER_ID))
        order = await core.recreate_order(order_id)
        await call.message.answer("Подождите, нужно все перепроверить...")
        return await send_preorder(call.from_user.id, order)

    else:
        raise NoActionFound(
            message_text="Данное действие не возможно выполнить с заказом!",
            detail="no_action_found__no_callback_action",
        )


@dp.callback_query_handler(review_cb.filter(), state=OrderReviewState.pick_stars)
async def pick_order_review_stars_handler(call, state, callback_data: dict = None):
    """
    Принимает количество звезд при оценке поездки
    """
    stars = int(callback_data[CB_STARS])
    order_id = int(callback_data[CB_ORDER_ID])
    is_driver = True if callback_data[IS_DRIVER] == 'True' else False
    await call.message.edit_reply_markup(reply_markup=None)
    if stars >= 3:
        # Если оценка нормальная то отправляем на сервер
        review = OrderReview(stars=stars)
        review = await core.set_order_review(order_id=order_id, review=review, is_driver=is_driver)
        await give_present_to_chat_id(chat_id=call.from_user.id, order_id=order_id)
        await main_menu_handler(
            None,
            state=state,
            chat_id=call.from_user.id,
            pre_text="Я принял ваш отзыв! Спасибо!\n\n",
        )
    else:
        # Если нет, то спрашиваем почему плохая оценка
        await state.update_data(stars=stars, order_id=order_id, is_driver=is_driver)
        await OrderReviewState.pick_text.set()
        await call.message.answer(
            "Мне жаль, что поездка оказалась неудачной, напишите что именно вас расстроило и мы обязательно сделаем работу над ошибками!"
        )


@dp.message_handler(state=OrderReviewState.pick_text)
async def pick_order_review_text_handler(message, state):
    data = await state.get_data()
    stars = data["stars"]
    order_id = data["order_id"]
    is_driver = data["is_driver"]

    review = OrderReview(stars=stars, text=message.text)
    review = await core.set_order_review(order_id=order_id, review=review, is_driver=is_driver)
    await give_present_to_chat_id(chat_id=message.from_user.id, order_id=order_id)
    await main_menu_handler(message, state, pre_text="Я принял ваш отзыв! Спасибо!\n\n")


@dp.message_handler(state=OrderState.get_comment_to_order)
async def pick_comment_to_order(message: types.Message, state: FSMContext):
    data = await state.get_data()
    order = data.get("order")
    updated_order = await core.update_order(id=order.id, data={"comment": message.text})
    await state.update_data(order=updated_order)
    await open_order(
        state=state,
        chat_id=message.from_user.id,
        pre_text=t.COMMENT_HAS_BEEN_ADDED + "\n\n",
    )
    await OrderState.pick_price.set()


@dp.message_handler(Command("open_order"), state="*")
async def open_order(
        message: types.Message = None,
        state: FSMContext = None,
        chat_id: int = None,
        pre_text: str = "",
        send_no_order_message: bool = True,
):
    """
    Функция открывает заказ, со всеми кнопками, применяет состояние

    Если нет активного заказа, то возвращает None, если есть, то возвращает активный заказ
    :param send_no_order_message: Если False, то пользователь не получит уведомление о том, что у него нет активных заказо
    """
    if state:
        data = await state.get_data()
    else:
        state = dp.current_state(chat=chat_id or message.from_user.id)
        data = await state.get_data()
        print(f"{data=}")
    order = await get_order(client_chat_id=chat_id or message.from_user.id, state=state)
    order_message_id: int = data.get("order_message_id")

    if not order:
        if send_no_order_message:
            await bot.send_message(
                chat_id or message.from_user.id,
                "В данный момент у вас нет активных заказов!",
            )
        return None

    await OrderState.order_in_progress.set()

    if order.status in (100, 101):
        order_message = await bot.send_message(
            chat_id or message.from_user.id,
            pre_text + order.as_text(),
            reply_markup=await order_keyboard(order=order),
        )
    else:
        order_message = await bot.send_photo(
            chat_id=chat_id or message.from_user.id,
            photo=order.get_driver_photo(),
            caption=pre_text + order.as_text(),
            reply_markup=await order_keyboard(order=order),
        )

    await state.update_data(order_message_id=order_message.message_id, order=order)

    if order_message_id:
        await bot.delete_message(
            chat_id=chat_id or message.from_user.id, message_id=order_message_id
        )

    return order


async def update_order_in_storage(
        client_chat_id: int, order: Order, driver_chat_id: int = None
) -> tuple:
    """
        Обновляет данные о заказе в хранилище водителя и клиента
    :param client_chat_id:
    :param driver_chat_id:
    :param order:
    :return:
    """
    driver_state = None
    if driver_chat_id:
        driver_state: FSMContext = dp.current_state(
            chat=driver_chat_id, user=driver_chat_id
        )
        await driver_state.update_data(ride=order)

    client_state: FSMContext = dp.current_state(
        chat=client_chat_id, user=client_chat_id
    )
    await client_state.update_data(order=order)

    return (client_state, driver_state)


async def get_order(client_chat_id: int, state: FSMContext = None):
    """
    Высокоуровневая функция для получения активного заказа клиента
    """
    if state:
        data = await state.get_data()
    else:
        state = dp.current_state(chat=client_chat_id)
        data = await state.get_data()
    order: Order = data.get("order")

    if not order:
        order = await core.get_active_order(client_chat_id=client_chat_id)

    return order


async def cancel_order(order: Order, status=ORDER_CANCELED_BY_CLIENT):
    """
    Высокоуровневая функция для отмены заказа
    """
    # Обновляем статус заказа
    order: Order = await core.update_order_status(order_id=order.id, status=status)
    client_chat_id = order.client.telegram_data.chat_id
    driver_chat_id = None
    # Если уже кто-то из водителей принял заказ
    if order.driver:
        driver_chat_id = order.driver.telegram_data.chat_id

    # Обновляем данные о заказе в хранилище
    client_state, driver_state = await update_order_in_storage(
        client_chat_id=client_chat_id, driver_chat_id=driver_chat_id, order=order
    )

    # Если есть хранилище водителя, то берем сообщение, которое транслирует геолокацию и удаляем его

    if status == ORDER_CANCELED_BY_CLIENT:
        client_text = t.ORDER_HAS_BEEN_CANCELED + "\n\n"
        driver_text = "К сожалению, клиент отменил заказ!\n\n"
    else:
        client_text = "Водитель отменил заказ!\n" + t.ORDER_HAS_BEEN_CANCELED + "\n\n"
        driver_text = "Заказ успешно отменён!" + "\n\n"
    # Открываем меню для клиента
    await main_menu_handler(
        None, chat_id=client_chat_id, state=client_state, pre_text=client_text
    )
    # Открываем главное меню для водителя, если он есть
    if driver_state:
        await main_menu_handler(
            None, chat_id=driver_chat_id, state=driver_state, pre_text=driver_text
        )


async def give_present_to_chat_id(chat_id: int, order_id: int):
    present = await core.get_present_by_order_id(order_id)
    if not present:
        return await bot.send_message(
            chat_id,
            f"За отзыв мы выдаём подарки! Но в данный момент подарков в вашем городе нет 😔 Мы проработаем этот момент!",
        )
    await present.message.send(chat_id)
