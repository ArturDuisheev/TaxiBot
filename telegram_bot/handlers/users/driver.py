import asyncio
import pprint

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.builtin import Command

from data import texts as t
from data.buttons import DRIVER_CABINET, EXIT, FINISH_WORK_DAY, START_WORK_DAY
from data.config import DEFAULT_LIVE_PERIOD
from handlers.users.main_menu import main_menu_handler
from handlers.users.order import cancel_order
from keyboards.inline import driver_cabinet_keyboard
from keyboards.inline.driver_cabinet import cb as driver_cabinet_cb
from keyboards.inline.order import (
    ACCEPT_ORDER,
    CANCEL_ORDER,
    CB_ACTION,
    CB_ORDER_ID,
    CB_STATUS,
    DECLINE_ORDER,
    GIVE_REVIEW,
    cancel_order_driver_keyboard,
    driver_cb,
    order_driver_keyboard,
    order_keyboard,
    review_keyboard,
    update_status_cb,
)
from loader import bot, core, dp, location_storage, qiwi
from middlewares.authentication import authenticate
from models.cabinet import User
from models.dispatcher import (
    DRIVER_IS_WAITING,
    ORDER_CANCELED_BY_DRIVER,
    RIDE_IS_FINISHED,
    RIDE_IS_STARTED,
    Location,
    Order,
)
from states import DriverMenu
from states.driver import OrderStateDriver
from states.order import OrderReviewState, OrderState
from utils.geolocator import getDistanceBetweenPointsNew
from .order import open_order, update_order_in_storage


@dp.message_handler(text=DRIVER_CABINET)
@dp.message_handler(Command("driver"))
@authenticate(fields=["driver"], extended=True)
async def open_driver_cabinet_handler(message: types.Message, update_message=False):
    """Открывает кабинет водителя"""
    user: User = message.user
    all_settings = await core.get_all_settings()
    if all_settings["cabinet_settings"].out_line_cost:
        text = t.DRIVER_CABINET_TEXT.format(
            name=user.first_name,
            balance=user.balance.as_text(),
            receiver=qiwi.number,
            user_id=user.id,
            driver_info=user.driver.as_text(),
            out_line_cost=all_settings["cabinet_settings"].out_line_cost,
            default_tariff_start=all_settings[
                "dispatcher_settings"
            ].default_tariff_start.strftime("%H:%M"),
            default_tariff_end=all_settings[
                "dispatcher_settings"
            ].default_tariff_end.strftime("%H:%M"),
        )
    else:
        text = t.DRIVER_CABINET_BASE_TEXT.format(
            name=user.first_name,
            driver_info=user.driver.as_text(),
        )
    if update_message:
        await message.edit_caption(
            text,
            reply_markup=await driver_cabinet_keyboard(
                user=message.user,
                out_line_cost=all_settings["cabinet_settings"].out_line_cost,
                hide_driver_cabinet=all_settings[
                    "cabinet_settings"
                ].hide_cabinet_button,
            ),
        )
    else:
        await message.answer_photo(
            photo=user.driver.get_photo_url(),
            caption=text,
            reply_markup=await driver_cabinet_keyboard(
                user=message.user,
                out_line_cost=all_settings["cabinet_settings"].out_line_cost,
                hide_driver_cabinet=all_settings[
                    "cabinet_settings"
                ].hide_cabinet_button,
            ),
        )


@dp.callback_query_handler(driver_cabinet_cb.filter())
async def driver_cabinet_handler(
        callback_query: types.CallbackQuery, state: FSMContext, callback_data: dict = None
):
    """
    Обрабатывает нажатия на кнопки личного кабинета водителя
    """
    action = callback_data["action"]

    if action == EXIT:
        # Выйти из меню
        await state.finish()
        await callback_query.message.delete()
        await main_menu_handler(
            None,
            pre_text=t.CLOSE_DRIVER_CABINET_TEXT,
            chat_id=callback_query.from_user.id,
        )
    elif action == START_WORK_DAY:
        # Начать рабочий день
        user, message_text = await core.make_driver_active(
            chat_id=callback_query.from_user.id
        )
        await callback_query.answer(t.START_WORK_DAY_TEXT, show_alert=True)
        await callback_query.message.answer(
            message_text
            + "\n\n⚠️ ОБЯЗАТЕЛЬНО ПРИШЛИТЕ МНЕ «ТРАНСЛЯЦИЮ ВАШЕЙ ГЕОПОЗИЦИИ» на 8 часов, иначе я не смогу присылать вам заказы!"
        )
        callback_query.message.user = user
        await open_driver_cabinet_handler(callback_query.message, update_message=True)

    elif action == FINISH_WORK_DAY:
        # Закончить рабочий день
        user = await core.finish_work_day(chat_id=callback_query.from_user.id)
        await callback_query.answer(t.END_WORK_DAY_TEXT, show_alert=True)
        callback_query.message.user = user
        await open_driver_cabinet_handler(callback_query.message, update_message=True)


@dp.message_handler(state="*", content_types=types.ContentTypes.LOCATION)
async def pick_user_location(message: types.Message, state: FSMContext = None):
    """
    Принимает геопозицию водителя
    """
    text = t.TAKE_GEO_TEXT

    if not message.location.live_period:
        text += t.NO_LIVE_LOCATION_WARNING_TEXT
    if message.location.live_period != 28800:
        text += t.SMALL_LIVE_PERIOD_WARNING
    await message.answer(text)
    await update_driver_location(message, state)


@dp.edited_message_handler(state="*", content_types=types.ContentTypes.LOCATION)
async def update_live_location_handler(
        message: types.Message, state: FSMContext = None
):

    await update_driver_location(message, state)


async def update_driver_location_send_client(chat_id: int):
    """
    Проверяет местонахождение водителя и пользователя
    """
    location: Location = await location_storage.get_data(key=str(chat_id))
    obj = await core.get_active_ride(driver_chat_id=chat_id)
    distance = getDistanceBetweenPointsNew(latitude1=location.latitude, longitude1=location.longitude,
                                           latitude2=obj.start_location.latitude, longitude2=obj.start_location.longitude)
    if distance <= 0.3:
        user_id = obj.client.telegram_data.chat_id
        await bot.send_message(chat_id=user_id, text="Водитель подъезжает")
        
        await location_storage.set_data(key=f'user_order_driver_chat_{chat_id}_is_sending', data=True)

async def update_driver_location_in_storage(chat_id: int, location: Location):
    await location_storage.set_data(key=str(chat_id), data=location)
    
    try:
        is_sending = await location_storage.get_data(f'user_order_driver_chat_{chat_id}_is_sending')
    except TypeError:
        is_sending = False
    if not is_sending:
        await update_driver_location_send_client(chat_id)

async def update_driver_location(message: types.Message, state: FSMContext = None):
    print("Обновление геопозиции: ", message.location)
    location = Location.parse_obj(message.location)
    chat_id = message.from_user.id
    await update_driver_location_in_storage(chat_id=chat_id, location=location)


@dp.callback_query_handler(driver_cb.filter(), state="*")
async def new_order_callback_handler(
        callback: types.CallbackQuery, callback_data: dict, state: FSMContext = None
):
    """
    Реагирует на нажатия на клавиатуру сообщенния-рассылки о новом заказе
    """
    if callback_data[CB_ACTION] == DECLINE_ORDER:
        # Если водитель нажал "Отказаться от заказа"
        await callback.message.delete()
        block_data = await core.analytics_driver_order_not_approved(order_id=int(callback_data[CB_ORDER_ID]),
                                                                chat_id=callback.from_user.id)
        if block_data["detail"].get("is_block", False):
            await callback.message.answer(block_data["detail"]["message"])

    elif callback_data[CB_ACTION] == ACCEPT_ORDER:
        # Если водитель нажал "Принять заказ"

        order: Order = await core.pick_order(
            order_id=int(callback_data[CB_ORDER_ID]),
            driver_chat_id=callback.from_user.id,
        )

        # Вводим его в состояние в процессе заказа
        await DriverMenu.order_in_progress.set()

        client_chat_id = order.client.telegram_data.chat_id
        client_state, driver_state = await update_order_in_storage(
            driver_chat_id=callback.from_user.id,
            client_chat_id=client_chat_id,
            order=order,
        )
        await open_order(
            state=client_state,
            chat_id=client_chat_id,
            pre_text=f"Водитель найден! К вам едет {order.driver.first_name}\n\n",
        )
        
        # Открываем меню заказа для водителя
        await open_ride(state=state, base_message=callback.message)

    elif callback_data[CB_ACTION] == CANCEL_ORDER:
        # Отмена заказа водителем
        order: Order = await get_ride(driver_chat_id=callback.from_user.id, state=state)
        await cancel_order(order, status=ORDER_CANCELED_BY_DRIVER)
        await callback.message.edit_reply_markup(reply_markup=None)
    
    elif callback_data[CB_ACTION] == GIVE_REVIEW:
        # Если пользователь нажал "Оценить поездку"
        # TODO: Сделать систему принятия оценки за поездку
        await OrderReviewState.pick_stars.set()
        print(f"{callback_data=}")
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.reply(
            "Спасибо, что оставляете оценку, это поможет нам улучшить сервис! Выберите количество звёзд от 1 до 5.",
            reply_markup=await review_keyboard(order_id=callback_data[CB_ORDER_ID], is_driver=True),
        )



@dp.message_handler(Command("open_ride"), state="*")
async def open_ride(
        message: types.Message = None,
        state: FSMContext = None,
        base_message: types.Message = None,
        send_client_location: bool = True,
        pre_text="",
        start_location_message_id=None,
):
    # Функция для открытия заказа, можно передать сообщение, которое будет отредактировано в текст заказа
    if not state:
        # Если состояние не передано или не задано
        state = dp.current_state()

    data = await state.get_data()
    order: Order = data.get("ride")
    if not order:
        message = base_message or message
        order = await core.get_active_ride(driver_chat_id=message.chat.id)
        if not order:
            return await message.answer("В данный момент у вас нет активного заказа")

    await state.update_data(ride=order)
    text = pre_text + order.as_text(for_driver=True)
    if base_message:
        # Если передано сообщение, которое нужно отредактировать, а не отправить новое
        ride_message = await base_message.edit_text(
            text, reply_markup=await order_driver_keyboard(order=order)
        )
    else:
        ride_message = await message.answer(
            text, reply_markup=await order_driver_keyboard(order=order)
        )

    await state.set_state(OrderStateDriver.order_start)
    await state.update_data(order_start=dict(latitude=order.start_location.latitude,
                                             longitude=order.start_location.longitude))
    # Если нужно отправить геопозицию клиента
    if send_client_location:
        start_location_message = await ride_message.reply_location(
            latitude=order.start_location.latitude,
            longitude=order.start_location.longitude,
        )

        # Поясняющее сообщение, для водителя
        start_location_message_description = await start_location_message.reply(
            "Откройте карту, чтобы построить маршрут до клиента."
        )

        start_location_message_id = start_location_message.message_id
        start_location_message_description_id = (
            start_location_message_description.message_id
        )
        await state.update_data(
            start_location_message_id=start_location_message_id,
            start_location_message_description_id=start_location_message_description_id,
        )
    await state.update_data(ride_message_id=ride_message.message_id)

    await DriverMenu.order_in_progress.set()


@dp.callback_query_handler(update_status_cb.filter(), state="*")
@dp.async_task
async def update_order_status_callback_handler(
        callback: types.CallbackQuery, callback_data: dict, state: FSMContext
):
    """Функция принимает callback для обновления статуса заказа"""
    order_id, status = int(callback_data.get(CB_ORDER_ID)), int(
        callback_data.get(CB_STATUS)
    )
    client_pre_text = ""
    order: Order = await core.update_order_status(order_id=order_id, status=status)
    client_state, driver_state = await update_order_in_storage(
        client_chat_id=order.client.telegram_data.chat_id,
        driver_chat_id=callback.from_user.id,
        order=order,
    )
    await callback.answer(t.ORDER_STATUS_CHANGED)
    if status == DRIVER_IS_WAITING:
        # Если водитель ожидает
        await location_storage.reset(f'dl:user_order_driver_chat_{callback.from_user.id}_is_sending')
        settings = await core.get_all_settings()
        settings = settings["dispatcher_settings"]
        client_pre_text = (
                t.DRIVER_DROVE_UP_AND_WAITING.format(
                    waiting_free_minutes=settings.waiting_free_minutes,
                    waiting_price=settings.waiting_price,
                )
                + "\n\n"
        )

    if status == RIDE_IS_STARTED:
        # Если поездка началась
        # Удаляем геопозицию точки А
        driver_data = await driver_state.get_data()
        start_location_message_id = driver_data.get("start_location_message_id")
        start_location_message_description_id = driver_data.get(
            "start_location_message_description_id"
        )
        if start_location_message_id and start_location_message_description_id:
            await bot.delete_message(
                callback.from_user.id, start_location_message_description_id
            )
            await bot.delete_message(callback.from_user.id, start_location_message_id)

        # Отправляем геопозицию точки Б
        finish_location_message = await bot.send_location(
            chat_id=callback.from_user.id,
            latitude=order.end_location.latitude,
            longitude=order.end_location.longitude,
        )
        await finish_location_message.reply(
            "Откройте карту, чтобы построить маршрут до точки Б."
        )
        # Отправляем клиенту сообщение, что поездка началась
        client_pre_text = t.THE_RIDE_IS_STARTED_HAVE_A_NICE_TRIP + "\n\n"
    if status == RIDE_IS_FINISHED:
        # Если поездка завершена
        client_pre_text = t.THE_DRIVE_IS_FINISHED + "\n\n"
    await open_order(
        state=client_state,
        chat_id=order.client.telegram_data.chat_id,
        pre_text=client_pre_text,
    )
    await open_ride(
        state=driver_state, base_message=callback.message, send_client_location=False
    )

    if status == RIDE_IS_FINISHED:
        await main_menu_handler(
            None, state=client_state, chat_id=order.client.telegram_data.chat_id
        )
        await main_menu_handler(
            None, state=driver_state, chat_id=order.driver.telegram_data.chat_id
        )

    if status == DRIVER_IS_WAITING:
        # Уведомление об окончании бесплатного времени ожидания
        settings = await core.get_all_settings()
        settings = settings["dispatcher_settings"]
        await asyncio.sleep(settings.waiting_free_minutes * 60)
        client_data = await client_state.get_data()
        order = client_data.get("order")
        if order.status == DRIVER_IS_WAITING:
            await bot.send_message(
                order.client.telegram_data.chat_id,
                text=f"{settings.waiting_free_minutes} мин. прошло, началось платное ожидание!",
            )
            await bot.send_message(
                order.driver.telegram_data.chat_id,
                text=(
                    "У клиента закончилось бесплатное время ожидания. "
                    "Дополнительная плата посчитается автоматически и будет включена в стоимость!"
                    f"\n\nЕсли клиент не выходит долгое время, то вы можете сами отменить этот "
                    f"заказ, нажав на кнопку «{CANCEL_ORDER}», и начать получать новые заказы!"
                ),
                reply_markup=await cancel_order_driver_keyboard(order=order),
            )


async def get_ride(driver_chat_id: int, state: FSMContext = None):
    """
    Высокоуровневая функция для получения активного заказа водителя
    """
    if state:
        data = await state.get_data()
    else:
        state = dp.current_state(chat=driver_chat_id)
        data = await state.get_data()
    order: Order = data.get("ride")

    if not order:
        order = await core.get_active_ride(driver_chat_id=driver_chat_id)

    return order
