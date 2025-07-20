# bot.py
import asyncio, logging
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from pyrogram.errors import FloodWait
from pymongo import MongoClient
from datetime import datetime, time
from urllib.parse import quote_plus
from keep_alive import keep_alive
import qrcode
from io import BytesIO

# ==== تنظیمات ربات ====
API_ID = 26438691
API_HASH = "b9a6835fa0eea6e9f8a87a320b3ab1ae"
BOT_TOKEN = "8172767693:AAHdIxn6ueG6HaWFtv4WDH3MjLOmZQPNZQM"
ADMIN_IDS = [7872708405, 6867380442]
CHANNEL_IDS = [-1002422139602, -1002601782167, -1002573288143, -1001476871294]  # 4 کانال / گروه

# ==== اتصال به MongoDB ====
MONGO_URI = "mongodb+srv://BoxOffice:136215@boxofficeuploaderbot.2howsv3.mongodb.net/?retryWrites=true&w=majority&appName=BoxOfficeUploaderBot"
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["BoxOfficeUploaderBot"]
films_col = db["films"]
users_col = db["users"]

app = Client("BoxOfficeUploaderBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ==== نگهدارنده وضعیت آپلود ====
upload_cache = {}

# ==== بازه حالت سکوت ====
SILENT_START = time(22, 0)
SILENT_END = time(10, 0)

def in_silent_mode():
    now = datetime.now().time()
    return now >= SILENT_START or now <= SILENT_END

def generate_qr(link):
    img = qrcode.make(link)
    buf = BytesIO()
    buf.name = "qr.png"
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf

def build_buttons(file_id, views, downloads, shares):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"👁 {views} | 📥 {downloads} | 🔁 {shares}", callback_data="noop")],
        [InlineKeyboardButton("📥 دریافت", callback_data=f"download_{file_id}"),
         InlineKeyboardButton("📊 آمار", callback_data=f"stats_{file_id}")]
    ])

async def is_subscribed(user_id):
    for ch in CHANNEL_IDS:
        try:
            member = await app.get_chat_member(ch, user_id)
            if member.status in ("left", "kicked"):
                return False
        except:
            return False
    return True

# ==== هندلر شروع ====
@app.on_message(filters.command("start"))
async def start(client, message: Message):
    user_id = message.from_user.id
    users_col.update_one({"_id": user_id}, {"$set": {"joined_at": datetime.utcnow()}}, upsert=True)

    if not await is_subscribed(user_id):
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 عضویت در کانال‌ها", url="https://t.me/BoxOffice_Irani")],
            [InlineKeyboardButton("✅ عضو شدم", callback_data="check_sub")]
        ])
        return await message.reply("لطفاً ابتدا در تمام کانال‌ها عضو شوید 👇", reply_markup=markup)

    if len(message.command) == 2:
        film_id = message.command[1]
        film = films_col.find_one({"film_id": film_id})
        if not film:
            return await message.reply("❌ فیلمی با این شناسه پیدا نشد.")

        await message.reply_photo("https://i.imgur.com/HBYNljO.png", caption="🎬 خوش‌آمدید!\nدر ادامه فایل‌های این فیلم را دریافت خواهید کرد.")

        sent_msgs = []
        for file in film["files"]:
            msg = await message.reply_document(
                file["file_id"],
                caption=file["caption"],
                reply_markup=build_buttons(file["_id"], file["views"], file["downloads"], file["shares"])
            )
            sent_msgs.append(msg)

        warn = await message.reply("⚠️ فایل‌ها تا ۳۰ ثانیه دیگر حذف می‌شوند. لطفاً ذخیره کنید.")
        sent_msgs.append(warn)

        await asyncio.sleep(30)
        for msg in sent_msgs:
            await msg.delete()
    else:
        await message.reply("برای دریافت فیلم، روی لینک اختصاصی داخل پست‌های کانال کلیک کنید.")

# ==== آپلود فایل توسط ادمین ====
@app.on_message(filters.document & filters.user(ADMIN_IDS))
async def admin_upload(client, message: Message):
    upload_cache[message.from_user.id] = {
        "step": "awaiting_id",
        "file_id": message.document.file_id
    }
    await message.reply("🆔 لطفاً شناسه فیلم را وارد کنید:")

@app.on_message(filters.text & filters.user(ADMIN_IDS))
async def admin_text(client, message: Message):
    user_id = message.from_user.id
    if user_id not in upload_cache:
        return

    data = upload_cache[user_id]

    if data["step"] == "awaiting_id":
        data["film_id"] = message.text.strip()
        data["step"] = "awaiting_caption"
        await message.reply("📝 لطفاً کپشن فایل را وارد کنید:")

    elif data["step"] == "awaiting_caption":
        caption = message.text.strip()
        new_file = {
            "_id": str(datetime.utcnow().timestamp()),
            "file_id": data["file_id"],
            "caption": caption,
            "views": 0,
            "downloads": 0,
            "shares": 0
        }

        film = films_col.find_one({"film_id": data["film_id"]}) or {"film_id": data["film_id"], "files": []}
        film["files"].append(new_file)
        films_col.update_one({"film_id": data["film_id"]}, {"$set": film}, upsert=True)

        await message.reply("✅ فایل ذخیره شد. فایل دیگری هم دارید؟", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ بله", callback_data="upload_more")],
            [InlineKeyboardButton("❌ خیر", callback_data=f"done_{data['film_id']}")]
        ]))

        del upload_cache[user_id]

# ==== هندلر دکمه‌ها ====
@app.on_callback_query()
async def callback_handler(client, callback: CallbackQuery):
    data = callback.data
    user_id = callback.from_user.id

    if data == "check_sub":
        if await is_subscribed(user_id):
            await callback.message.edit("✅ عضویت تأیید شد. لطفاً مجدد /start بزنید.")
        else:
            await callback.answer("❌ هنوز عضو نیستید!", show_alert=True)

    elif data.startswith("done_"):
        film_id = data.split("_")[1]
        deep_link = f"https://t.me/BoxOfficeUploaderBot?start={film_id}"
        qr = generate_qr(deep_link)
        await callback.message.reply_photo(qr, caption=f"🎬 لینک اختصاصی فیلم:\n{deep_link}")

    elif data.startswith("download_"):
        file_id = data.split("_")[1]
        films_col.update_one({"files._id": file_id}, {"$inc": {"files.$.downloads": 1}})
        await callback.answer("✅ در حال دانلود...", show_alert=False)

    elif data.startswith("stats_"):
        file_id = data.split("_")[1]
        film = films_col.find_one({"files._id": file_id})
        for file in film["files"]:
            if file["_id"] == file_id:
                stats = f"👁 بازدید: {file['views']} | 📥 دانلود: {file['downloads']} | 🔁 اشتراک: {file['shares']}"
                await callback.answer(stats, show_alert=True)

    elif data == "upload_more":
        await callback.message.reply("📤 لطفاً فایل بعدی را ارسال کنید.")

# ==== اجرای امن با مدیریت FloodWait ====
async def start_bot():
    while True:
        try:
            await app.start()
            print("✅ Bot started")
            await idle()
            break
        except FloodWait as e:
            print(f"🚫 FloodWait: صبر {e.value} ثانیه‌ای لازم است.")
            await asyncio.sleep(e.value)
        except Exception as ex:
            logging.exception("❌ خطای غیرمنتظره:")
            break

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    keep_alive()
    asyncio.run(start_bot())
