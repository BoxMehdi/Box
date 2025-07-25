import os
import ssl
import certifi
import asyncio
import logging
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

# تنظیمات اولیه
API_ID = 26438691
API_HASH = "b9a6835fa0eea6e9f8a87a320b3ab1ae"
BOT_TOKEN = "8172767693:AAHdIxn6ueG6HaWFtv4WDH3MjLOmZQPNZQM"
ADMINS = [7872708405, 6867380442]
REQUIRED_CHANNELS = ["@BoxOffice_Irani", "@BoxOfficeMoviiie", "@BoxOffice_Animation", "@BoxOfficeGoftegu"]

# مقدار MONGO_URI رو جایگزین کن با کانکشن استرینگ MongoDB Atlas خودت
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://username:password@cluster.mongodb.net/mydb?retryWrites=true&w=majority")

# لاگ سطح INFO
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')

print("OpenSSL version:", ssl.OPENSSL_VERSION)

# تابع ایجاد اتصال MongoDB با Retry
def connect_mongo(uri, max_retries=5):
    for attempt in range(1, max_retries+1):
        try:
            client = MongoClient(
                uri,
                tls=True,
                tlsCAFile=certifi.where(),
                serverSelectionTimeoutMS=30000,
                connectTimeoutMS=30000,
            )
            # این خط برای اطمینان از اتصال به سرور است
            client.server_info()
            logging.info("✅ اتصال به MongoDB برقرار شد.")
            return client
        except ServerSelectionTimeoutError as e:
            logging.error(f"❌ خطا در اتصال به MongoDB (تلاش {attempt} از {max_retries}): {e}")
            if attempt == max_retries:
                logging.error("اتصال به دیتابیس برقرار نشد، برنامه متوقف شد.")
                raise
            else:
                logging.info("در حال تلاش مجدد اتصال به MongoDB...")
                asyncio.sleep(5)

# ساخت کلاینت MongoDB
try:
    mongo_client = connect_mongo(MONGO_URI)
except Exception:
    # اگر اتصال نشد، برنامه متوقف می‌شود
    exit(1)

db = mongo_client.get_database("boxoffice")
upload_states_col = db.get_collection("upload_states")
files_col = db.get_collection("files")

app = Client("BoxOfficeUploaderBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# چک کردن عضویت در کانال‌ها
async def check_subscriptions(user_id):
    for channel in REQUIRED_CHANNELS:
        try:
            member = await app.get_chat_member(channel, user_id)
            if member.status in ["left", "kicked"]:
                return False
        except Exception as e:
            logging.warning(f"خطا در بررسی عضویت کاربر {user_id} در {channel}: {e}")
            return False
    return True

# دستور استارت ساده
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id
    text = "👋 سلام!\nبرای دسترسی به فیلم‌ها ابتدا باید عضو کانال‌های ما باشید."
    buttons = [
        [InlineKeyboardButton("عضویت در @BoxOffice_Irani", url="https://t.me/BoxOffice_Irani")],
        [InlineKeyboardButton("عضویت در @BoxOfficeMoviiie", url="https://t.me/BoxOfficeMoviiie")],
        [InlineKeyboardButton("عضویت در @BoxOffice_Animation", url="https://t.me/BoxOffice_Animation")],
        [InlineKeyboardButton("عضویت در @BoxOfficeGoftegu", url="https://t.me/BoxOfficeGoftegu")],
        [InlineKeyboardButton("✅ من عضو شدم", callback_data="check_subs")],
    ]
    await message.reply(text, reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex("^check_subs$"))
async def check_subs_callback(client: Client, callback_query):
    user_id = callback_query.from_user.id
    if await check_subscriptions(user_id):
        await callback_query.answer("🎉 تبریک! شما عضو همه کانال‌ها هستید.", show_alert=True)
        await callback_query.message.edit("✅ عضویت شما تایید شد. اکنون می‌توانید فایل‌ها را دریافت کنید.")
    else:
        await callback_query.answer("❌ شما هنوز عضو همه کانال‌ها نیستید!", show_alert=True)

# آپلود فایل فقط برای ادمین‌ها (نمونه)
@app.on_message(filters.document & filters.user(ADMINS))
async def upload_handler(client: Client, message: Message):
    admin_id = message.from_user.id
    # ذخیره فایل در MongoDB (فقط مثال، معمولاً فایل‌ها را در تلگرام نگهداری می‌کنیم)
    file_info = {
        "file_id": message.document.file_id,
        "file_name": message.document.file_name,
        "admin_id": admin_id,
    }
    files_col.insert_one(file_info)
    await message.reply("🎉 فایل با موفقیت ذخیره شد و آماده استفاده است.")

# خطاهای کلی
@app.on_message(filters.private)
async def unknown_message(client: Client, message: Message):
    await message.reply("❌ دستور شناخته نشده! از /start استفاده کنید.")

if __name__ == "__main__":
    print("🤖 ربات BoxOfficeUploaderBot در حال اجراست...")
    app.run()
