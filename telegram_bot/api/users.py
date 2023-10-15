from typing import Union

from aiogram import types
from models.cabinet import User, initialize_user
from models.referral import Coupon

from utils.misc.logging import logger

from .utils import (
    parse_get_user_exceptions,
    parse_user_data,
    patch_request,
    post_request,
)


class UserAPIMethods:
    """
    Абстрактный класс с методами для взаимодействия с данными пользователей через API
    """

    async def _register_user(self, json_data: dict, user_photo_path: str = None):
        """
            Raw метод для регистрации пользователей
        :param json_data:
        :return:
        """
        if user_photo_path:
            files = {"photo": ("user_avatar.jpg", open(user_photo_path, "rb"))}
        else:
            files = None
        response = await post_request(
            session=self.session,
            url=self.base_url() + "users/registerFromTelegram/",
            data=json_data,
            files=files,
            headers=self.headers,
        )
        return response

    async def register_user(
        self, user_data: dict, user_photo_path: str = None, mentor_chat_id: int = None
    ) -> dict:
        """
            Метод для регистрации пользователей
        :param user_data:
        :return:
        """
        # Форматирует данные в необходимый формат для API
        json_data = parse_user_data(from_user=user_data)
        if mentor_chat_id:
            json_data["mentor_chat_id"] = mentor_chat_id

        # Делает запрос в API

        response = await self._register_user(
            json_data=json_data, user_photo_path=user_photo_path
        )

        if response.status == 201:
            # Если создание пользователя прошло успешно
            return initialize_user(await response.json())
        else:
            # Если пользователь уже создан или API недоступно
            return None

    async def _create_driver(self, user_data: dict):
        response = await post_request(
            session=self.session,
            url=self.base_url() + "users/registerDriver/",
            json_data=user_data,
            headers=self.headers,
        )
        return response


    async def create_driver(self, user_data: dict) -> dict:
        response = await self._create_driver(user_data=user_data)
        if response.status == 201:
            return True
        else:
            return False



    async def get_or_create_user(self, from_user: dict) -> User:
        """
            Возвращает данные пользователя из API
        :param chat_id:
        :return:
        """
        json_data = parse_user_data(from_user=from_user)
        response = await post_request(
            session=self.session,
            url=self.base_url() + "users/getOrCreateUserFromTelegram/",
            data=json_data,
            headers=self.headers,
        )
        json_data = await response.json()
        return initialize_user(json_data)

    async def get_user_by_chat_id(
        self, chat_id: int, extended=False, with_password=False
    ) -> User:
        """
        Возвращает пользователя или ничего, если данный пользователь не зарегистрирован
        """
        if with_password:
            url = self.base_url() + "users/getUserFromTelegram/"
        elif extended:
            url = self.base_url() + "users/getUserExtended/"
        else:
            url = self.base_url() + "users/getUserFromTelegram/"

        response = await post_request(
            session=self.session,
            url=url,
            json_data={"chat_id": chat_id},
            headers=self.headers,
        )

        json_data = await response.json()
        return initialize_user(json_data)

    async def get_user_or_error(self, message: types.Message):
        """
        Получает пользователя по сообщению, обрабатывает ошибки. При ошибке прекращает обработку Хэндлера и уведомлят пользователя об ошибке.
        """
        try:
            user = await self.get_user_by_chat_id(chat_id=message.from_user.id)
        except Exception as E:
            await parse_get_user_exceptions(message, E)

        return user

    async def update_users_location(self, json_data: list):
        """
        Принимает данные для обновления геопозиции пользователей
        :param json_data: Спикок объектов, в которых есть chat_id, latitude, longitude
        """
        response = await patch_request(
            session=self.session,
            url=self.base_url() + "users/updateUserLocations/",
            json_data=json_data,
            headers=self.headers,
        )
        return None

    async def update_user_balance(self, user_id: int, value: Union[int, float]):
        """
        Обновляет баланс пользователя
        """
        json_data = {"pk": user_id, "value": value}
        response = await post_request(
            session=self.session,
            url=self.base_url() + "users/updateUserBalance/",
            json_data=json_data,
            headers=self.headers,
        )
        return initialize_user(await response.json())

    async def make_driver_active(self, chat_id: int) -> "message":
        """
        Отправляет запрос в API, который делает водителя активным
        Возвращает обновленные данные пользователя и сообщение, в котором содержится информация о списании
        """
        json_data = {"chat_id": chat_id}
        response = await post_request(
            session=self.session,
            url=self.base_url() + "users/outOnTheLineDriver/",
            json_data=json_data,
            headers=self.headers,
        )
        data = await response.json()
        return (initialize_user(data.get("user")), data.get("message"))

    async def finish_work_day(self, chat_id: int):
        """
        Отправляет запрос в API для завершения рабочего дня
        Возвращает обновленные данные пользователя
        """

        json_data = {"chat_id": chat_id}
        response = await post_request(
            session=self.session,
            url=self.base_url() + "users/finishWorkDay/",
            json_data=json_data,
            headers=self.headers,
        )

        return initialize_user(await response.json())

    async def update_user(self, user_id: int, **data):
        response = await patch_request(
            session=self.session,
            url=self.base_url() + f"users/updateUser/{user_id}/",
            json_data=data,
            headers=self.headers,
        )

        return initialize_user(await response.json())
