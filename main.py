import asyncio
import threading
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from urllib.parse import quote_plus
from flask import Flask

API_ID = 26438691
API_HASH = "b9a6835fa0eea6e9f8a320b3ab1ae"
BOT_TOKEN = "8031070707:AAEf5KDsmxL2x1_iZ_A1PgrGuqPL29TaW8A"
ADMIN_IDS = [7872708405, 6867380442]

MONGO_USER = "BoxOffice"
MONGO_PASS = "136215"
MONGO_CLUSTER = "boxofficeuploaderbot.2howsv3.mongodb.net"

MONGO_PASS_ENCODED = quote_plus(MONGO_PASS)
MONGO_URI = f"mongodb+srv://{MONGO_USER}:{MONGO_PASS_ENCODED}@{MONGO_CLUSTER}/?retryWrites=true&w=majority&appName=BoxOfficeUploaderBot"

mongo_client = MongoClient(MONGO_URI)
db = mongo_client["boxoffice_db"]
files_collection = db["files"]
uploads_in_progress = db["uploads_in_progress"]

REQUIRED_CHANNELS = [
    "BoxOffice_Animation",
    "BoxOfficeMoviiie",
    "BoxOffice_Irani",
    "BoxOfficeGoftegu"
]

app = Flask("")

@app.route("/")
def home():
    return "I am alive!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

bot = Client("boxoffice_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# تابع user_is_subscribed و بقیه هندلرها اینجا می‌آیند (کد کامل مثل قبل)

# برای مثال فقط یک هندلر ساده start:
@bot.on_message(filters.private & filters.command("start"))
async def start_handler(client, message):
    await message.reply("ربات فعال است و پاسخ می‌دهد ✅")

if __name__ == "__main__":
    keep_alive()  # اجرای وب‌سرور Flask در ترد جدا
    bot.run()
