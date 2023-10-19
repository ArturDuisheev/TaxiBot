from models.dispatcher import initialize_order, OrderReview
from .utils import post_request, parse_order_data_from_state, patch_request


class OrderAPIMethods:
    """
    Абстрактный класс для методов взаимодействия с заказами
    """

    async def _create_order(self, json_data: dict):
        response = await post_request(
            session=self.session,
            url=self.base_url() + "orders/createOrder/",
            json_data=json_data,
            headers=self.headers,
        )
        return await response.json()

    async def create_order(self, data: dict):
        json_data = parse_order_data_from_state(data)
        print(json_data, 'json data')
        order_data = await self._create_order(json_data=json_data)

        return initialize_order(order_data)

    async def recreate_order(self, order_id: int):
        json_data = {"order_id": order_id}
        response = await post_request(
            session=self.session,
            url=self.base_url() + "orders/reCreateOrder/",
            json_data=json_data,
            headers=self.headers,
        )
        order_data = await response.json()
        return initialize_order(order_data)

    async def create_order_revision(self, order_id: int):
        json_data = {"order_id": order_id}
        await post_request(
            session=self.session,
            url=self.base_url() + "orders/createOrderRevision/",
            json_data=json_data,
            headers=self.headers,
        )

    async def update_order(self, id: int, data: dict):
        """
        Обновляет указанные данные
        """
        response = await patch_request(
            session=self.session,
            url=self.base_url() + f"orders/updateOrder/{id}",
            json_data=data,
            headers=self.headers,
        )
        order_data = await response.json()
        return initialize_order(order_data)

    async def pick_order(self, order_id: int, driver_chat_id: int):
        json_data = {"chat_id": driver_chat_id, "order_id": order_id}
        response = await post_request(
            session=self.session,
            url=self.base_url() + "orders/driverPickOrder/",
            json_data=json_data,
            headers=self.headers,
        )

        return initialize_order(await response.json())

    async def update_order_status(self, order_id: int, status: int):
        json_data = {"status": int(status)}

        response = await patch_request(
            session=self.session,
            url=self.base_url() + f"orders/updateOrderStatus/{order_id}/",
            json_data=json_data,
            headers=self.headers,
        )

        return initialize_order(await response.json())

    async def get_active_order(self, client_chat_id: int):
        # Возвращает активный заказ клиента
        json_data = {"chat_id": int(client_chat_id)}
        response = await post_request(
            session=self.session,
            url=self.base_url() + "orders/getClientActiveOrder/",
            json_data=json_data,
            headers=self.headers,
        )
        return initialize_order(await response.json())

    async def get_active_ride(self, driver_chat_id: int):
        # Возвращает активный заказ водителя
        json_data = {"chat_id": int(driver_chat_id)}
        response = await post_request(
            session=self.session,
            url=self.base_url() + "orders/getDriverActiveRide/",
            json_data=json_data,
            headers=self.headers,
        )
        return initialize_order(await response.json())

    async def set_order_review(self, order_id, review: OrderReview, is_driver):
        json_data = {"order_id": int(order_id), "review": review.dict(), "is_driver": is_driver}

        response = await post_request(
            session=self.session,
            url=self.base_url() + "orders/setReview/",
            json_data=json_data,
            headers=self.headers,
        )

        return OrderReview.parse_obj(await response.json())

    async def analytics_driver_order_not_approved(self, order_id: int, chat_id: int) -> bool:
        json_data = {"chat_id": int(chat_id)}
        print(json_data, order_id)
        response = await self.session.post(self.base_url() + f"analytics/driver/order/{order_id}", json=json_data)
        print(response, 'dadada', response.status)
        # response = await post_request(
        #     session=self.session,
        #     url=self.base_url() + f"analytics/driver/order/{order_id}",
        #     json_data=json_data,
        #     headers=self.headers,
        # )
        data = await response.json()
        return data