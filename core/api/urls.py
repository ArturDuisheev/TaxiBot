from cabinet.api import (
    DriverRegisterAPI,
    GetAllSettingsAPIView,
    GetOrCreateUserFromTelegramAPI,
    GetUserExtendedAPI,
    GetUserFromTelegramAPI,
    OutOnTheLineDriver,
    RegisterUserFromTelegramAPI,
    UpdateUserAPIView,
    finish_driver_work_day,
    update_user_balance_api_view,
    update_users_location, GetUserApiByTelegramTokenAuth,
)
from dispatcher.api import (
    CreateOrderAPI,
    DriverAnalyticsOrderAPIView,
    DriverPickOrderAPI,
    ReCreateOrderAPI,
    UpdateOrderAPI,
    UpdateOrderStatusAPI,
    create_order_revision_api_view,
    get_active_order_api_view,
    get_active_ride_api_view,
    get_price_api_view,
    set_order_review,
    GetMapCenterAPIView, GetActiveOrderByTelegramAuthToken,
)
from django.urls import path
from referral.api import get_present_from_order, pick_coupon_from_telegram

urlpatterns = [
    path("users/registerFromTelegram/", RegisterUserFromTelegramAPI.as_view()),
    path("users/registerDriver/", DriverRegisterAPI.as_view()),

    path(
        "users/getOrCreateUserFromTelegram/", GetOrCreateUserFromTelegramAPI.as_view()
    ),
    path("users/getUserFromTelegram/", GetUserFromTelegramAPI.as_view()),
    path("users/GetUserApiByTelegramTokenAuth/<str:token>/", GetUserApiByTelegramTokenAuth.as_view()),
    path("users/getUserExtended/", GetUserExtendedAPI.as_view()),
    path("users/updateUserLocations/", update_users_location),
    path("users/updateUserBalance/", update_user_balance_api_view),
    path("users/outOnTheLineDriver/", OutOnTheLineDriver.as_view()),
    path("users/finishWorkDay/", finish_driver_work_day),
    path("users/updateUser/<int:pk>/", UpdateUserAPIView.as_view()),

    path("orders/createOrder/", CreateOrderAPI.as_view()),
    path("orders/reCreateOrder/", ReCreateOrderAPI.as_view()),
    path("orders/updateOrder/<int:pk>", UpdateOrderAPI.as_view()),
    path("orders/driverPickOrder/", DriverPickOrderAPI.as_view()),
    path("orders/updateOrderStatus/<int:order_id>/", UpdateOrderStatusAPI.as_view()),
    path("orders/getClientActiveOrder/", get_active_order_api_view),
    path("orders/getDriverActiveRide/", get_active_ride_api_view),
    path("orders/setReview/", set_order_review),
    path("orders/createOrderRevision/", create_order_revision_api_view),
    path("orders/getPrice/", get_price_api_view),
    path("orders/getActiveByTelegramAuthToken/<str:token>/", GetActiveOrderByTelegramAuthToken.as_view()),

    path("coupons/pickCouponFromTelegram/", pick_coupon_from_telegram),
    path("presents/getPresentFromOrder/", get_present_from_order),

    path("getAllSettings/", GetAllSettingsAPIView.as_view()),
    path("map-center/", GetMapCenterAPIView.as_view()),

    path('analytics/driver/order/<int:pk>', DriverAnalyticsOrderAPIView.as_view()),
]
