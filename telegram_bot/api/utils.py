from utils.misc.logging import logger
from typing import Union

import aiohttp
from aiogram import types
from aiogram.dispatcher.handler import CancelHandler
from utils.exceptions import BadCoreRequest, CoreError, UserNotFound

from .exceptions import CORE_ERRORS


def compose_data(json_data=None, files=None) -> aiohttp.formdata.FormData:
    """
        Возвращает объединенные данные для отправки multipart/form-data запроса
    :param json_data:
    :param files:
    :return:
    """
    data = aiohttp.formdata.FormData()

    if json_data:
        for key, value in json_data.items():
            data.add_field(key, str(value))

    if files:
        for key, f in files.items():
            filename, fileobj = f
            data.add_field(key, fileobj, filename=filename)

    return data


async def post_request(
    session: aiohttp.ClientSession,
    url: str,
    data: dict = None,
    files: dict = None,
    headers: dict = None,
    json_data: dict = None,
) -> aiohttp.ClientResponse:
    """
    Отправляет POST запрос к Core API.
    Автоматически объединяет файлы и данные, либо отдельно json, при необходимости
    Функция универсальна для отправки любых запросов на сервер
    """

    # Если данные отправляются в json
    logger.info(url)
    if json_data:
        new_headers = headers.copy()
        new_headers["Content-Type"] = "application/json"
        response = await session.post(url, json=json_data, headers=new_headers)

    # application/x-www-form-urlencoded
    else:
        # Объединяем
        req = compose_data(data, files)
        # Отправляем асинхронный запрос
        response = await session.post(url, data=req)

    # Возвращаем ответ
    await check_response(response)
    return response


async def patch_request(
    session: aiohttp.ClientSession,
    url: str,
    data: dict = None,
    files: dict = None,
    headers: dict = None,
    json_data: Union[list, dict] = None,
) -> aiohttp.ClientResponse:
    """
    Отправляет PATCH запрос к Core API.
    Автоматически объединяет файлы и данные, либо отдельно json, при необходимости
    Функция универсальна для отправки любых запросов на сервер
    """

    # Если данные отправляются в json
    logger.info(url)
    if json_data:
        headers = headers.copy()
        headers["Content-Type"] = "application/json"
        response = await session.patch(url, json=json_data, headers=headers)

    # application/x-www-form-urlencoded
    else:
        # Объединяем
        req = compose_data(data, files)
        # Отправляем асинхронный запрос
        response = await session.patch(url, data=req, headers=headers)

    # Возвращаем ответ
    await check_response(response)
    return response


async def get_request(
    session: aiohttp.ClientSession,
    url: str,
    json_data: dict = None,
    headers: dict = None,
) -> aiohttp.ClientResponse:
    response = await session.get(url, json=json_data, headers=headers)
    return response


async def check_response(response: aiohttp.ClientResponse) -> bool:
    """
        Проверяет запрос, если вдруг статус плохой, выдает ошибку
    :param response:
    :return:
    """
    logger.info(f"<Response status {response.status}>")

    await parse_response_errors(response)
    if response.status in range(200, 301):
        return True
    elif response.status == 400:
        raise BadCoreRequest(await response.json())
    else:
        raise CoreError(await response.json())


async def parse_response_errors(response):
    data = await response.json()

    # Берет шорткод ошибки
    detail = data.get("detail")
    print(f"{detail=}")
    if detail in CORE_ERRORS:
        # Возбуждает соответствующее исключение
        raise CORE_ERRORS[detail]


async def parse_get_user_exceptions(message: types.Message, exception: Exception):
    """
        Обрабатывает ошибку и останавливает обработку хэндлера
    :param message:
    :param exception:
    :return:
    """
    text = f"Возника ошибка!\n\n<code>{exception.args}</code>"
    if isinstance(exception, UserNotFound):
        text = "Вы не зарегистрированы в системе. Пожалуйста отправьте /start, чтобы зарегистрироваться."
    elif isinstance(exception, CoreError):
        text = "Ошибка в ядре системы. Подождите 15 минут, мы уже работаем над её исправлением."
    await message.answer(text)
    # Отменяет обработку хендлера, обработчик не запуститься
    raise CancelHandler()


def parse_user_data(from_user: dict):
    return {
        "first_name": from_user.first_name,
        "username": from_user.username or f"{from_user.id}",
        "chat_id": from_user.id,
    }


def parse_order_data_from_state(state_data: dict):
    """
    Возвращает json-dict для отправки запроса к API.
    Принимает данные переданные из машины состояний при оформлении заказа
    """
    return {
        "client": state_data.get("client").id,
        "start_location": state_data.get("start_location").dict(),
        "end_location": state_data.get("end_location").dict(),
        "payment_method": state_data.get("payment_method"),
        "client_phone": state_data.get("client_phone"),
        "coupon": state_data.get("coupon"),
        "is_need_baby_chair": state_data.get("is_need_baby_chair"),
        "comment": state_data.get("comment"),
        "entrance": state_data.get("entrance"),
    }
