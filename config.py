import os
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME")

ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS").split(",")))
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB")

REQUIRED_CHANNELS = os.getenv("REQUIRED_CHANNELS").split(",")

WELCOME_IMAGE = os.getenv("WELCOME_IMAGE")
WELCOME_TEXT = os.getenv("WELCOME_TEXT")

JOIN_LINK_1 = os.getenv("JOIN_LINK_1")
JOIN_LINK_2 = os.getenv("JOIN_LINK_2")
JOIN_LINK_3 = os.getenv("JOIN_LINK_3")
JOIN_LINK_4 = os.getenv("JOIN_LINK_4")
