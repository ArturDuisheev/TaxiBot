from pathlib import Path

from environs import Env
from dotenv import load_dotenv
import os
# Теперь используем вместо библиотеки python-dotenv библиотеку environs
load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent
env = Env()
print(env)
DEBUG = 1

BOT_TOKEN = os.getenv("BOT_TOKEN")  # Забираем значение типа str
DADATA_TOKEN = os.getenv("DADATA_TOKEN")
ADMINS = [805964909, 1143520926]  # Тут у нас будет список из админов
PAY_TOKEN = os.getenv("PAY_TOKEN")
for i in range(len(ADMINS)):
    ADMINS[i] = int(ADMINS[i])

IP = "0.0.0.0"  # Тоже str, но для айпи адреса хоста
WEB_BOT_URL = "https://t.me/taxiber_testing_bot"

# webhook settings
CORE_TOKEN = os.getenv("CORE_TOKEN")
WEBHOOK_HOST = "localhost"
# if DEBUG:
#     WEBHOOK_PATH = '/'+ CORE_TOKEN + '/'
# else:
#     WEBHOOK_PATH = '/_telegram_bot/' + CORE_TOKEN + '/'

WEBHOOK_PATH = "/_telegram_bot/" + CORE_TOKEN + "/"

WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

QIWI_WEBHOOK_PATH = f"{WEBHOOK_PATH}" + "qiwi/"
QIWI_WEBHOOK_URL = f"{WEBHOOK_HOST}{QIWI_WEBHOOK_PATH}"

MAILING_WEBHOOK_PATH = f"{WEBHOOK_PATH}" + "mailing/"
ORDER_REVISION_NOTIFY_WEBHOOK_PATH = WEBHOOK_PATH + "orderRevisionNotify/"

# webserver settings
WEBAPP_HOST = IP
WEBAPP_PORT = 8080


CORE_TOKEN = CORE_TOKEN
QIWI_TOKEN =""
QIWI_PHONE_NUMBER = ""

BASE_URL = os.getenv("BASE_URL")
CORE_BASE_URL = BASE_URL + "/api/"
CORE_HEADERS = {}

CABINET_LOGIN_URL = BASE_URL + "/cabinet/telegram_auth_token_login/%s/"

MEDIA_URL = BASE_DIR / "data/media/"
ICONS_MEDIA_URL = MEDIA_URL / "telegram_icons"
LOGGING_FILE_PATH = BASE_DIR / "data" / "logs" / "logging.log"


REDIS_NAME = "77.222.37.151"
REDIS_PORT = 6380
REDIS_LOCATION_DB = 1
REDIS_FSM_DB = 2
# !!! 3 db number занят ядром, если находятся на одном сервере
REDIS_PASSWORD = "foobared"

DRIVER_LOCATION_PREFIX = "dl"

UPDATE_DRIVER_LOCATION_PERIOD = 5
UPDATE_DRIVER_LOCATION_LOGGER_ID = "UPDATE_LOCATION"
UPDATE_DRIVER_LOCATION_FILE = BASE_DIR / "data" / "logs" / "update_locations.log"
QIWI_LOGGER_ID = "QIWI_LOGGER"
QIWI_LOGGER_FILE = BASE_DIR / "data" / "logs" / "qiwi.log"

DEFAULT_LIVE_PERIOD = 7200
