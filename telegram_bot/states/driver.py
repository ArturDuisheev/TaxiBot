from aiogram.dispatcher.filters.state import State, StatesGroup


class DriverMenu(StatesGroup):
    """
    Меню для водителей
    """

    order_in_progress = State()


class OrderStateDriver(StatesGroup):

    order_start = State()


class DriverRegister(StatesGroup):
    """
    Регистрация водителя
    """
    car_brand = State()
    car_number = State()
    car_color = State()
    phone_number = State()
    photo = State()
    baby_chair = State()
