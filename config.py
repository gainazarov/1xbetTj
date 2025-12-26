import logging
from logging.handlers import RotatingFileHandler
import os
from typing import List

from dotenv import load_dotenv


load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SITE_URL = os.getenv("SITE_URL", "https://1xbet.tj")
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "")
DB_PATH = os.getenv("DB_PATH", "bot.db")
LOG_FILE = os.getenv("LOG_FILE", "bot.log")


if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан. Укажите его в файле .env")


def _parse_admin_ids(raw: str) -> List[int]:
    ids: List[int] = []
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            logging.warning("Не удалось распарсить admin id: %s", part)
    return ids


ADMIN_IDS: List[int] = _parse_admin_ids(ADMIN_IDS_RAW)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


logger = logging.getLogger()
logger.setLevel(logging.INFO)

formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s")

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)

file_handler = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
file_handler.setFormatter(formatter)

logger.handlers.clear()
logger.addHandler(stream_handler)
logger.addHandler(file_handler)
