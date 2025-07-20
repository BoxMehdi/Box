import asyncio
import logging
from datetime import datetime, time
from pyrogram import Client, filters, idle
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait
from pymongo import MongoClient
from urllib.parse import quote_plus
import qrcode
from io import BytesIO
from keep_alive import keep_alive

# ========== تنظیمات ==========
API_ID = 26438691
API_HASH = "b9a6835fa0eea6e9f8a87a320b3ab1ae"
BOT_TOKEN = "8031070707:AAEQXSV9QGNgH4Hb6_ujsb1kE-DVOVvOmAU"
ADMIN_IDS = [7872708405, 6867380442]
CHANNEL_IDS = [-1002422139602, -1002601782167, -1002573288143, -1001476871294]
MONGO_URI = "mongodb+srv://BoxOffice:136215@boxofficeuploaderbot.2howsv3.mongodb.net/?retryWrites=true&w=majority&appName=BoxOfficeUploaderBot"

# ========== اتصال به MongoDB ==========
mongo = MongoClient(MONGO_URI)
db = mongo["BoxOfficeUploaderBot"]
films_col = db["films"]
users_col = db["users"]

# ========== راه‌اندازی ربات ==========
app = Client("BoxOfficeUploaderBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
upload_cache = {}

# ========== زمان حالت سکوت ==========
SILENT_START = time(22, 0)
SILENT_END = time(10, 0)

def in_silent():
    now = datetime.now().time()
    return now >= SILENT_START or now <= SILENT_END

def generate_qr(link):
    img = qrcode.make(link)
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.name = "qr.png"
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

# ========== استارت ==========
@app.on_message(filters.command("start"))
async def start(client, message: Message):
    user_id = message.from_user.id
    users_col.update_one({"_id": user_id}, {"$set": {"joined": datetime.utcnow()}}, upsert=True)

    if not await is_subscribed(user_id):
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 عضویت در کانال‌ها", url="https://t.me/BoxOffice_Irani")],
            [InlineKeyboardButton("✅ عضو شدم", callback_data="check_sub")]
        ])
        return await message.reply("لطفاً ابتدا در کانال‌ها عضو شوید 👇", reply_markup=markup)

    if len(message.command) == 2:
        film_id = message.command[1]
        film = films_col.find_one({"film_id": film_id})
        if not film:
            return await message.reply("❌ فیلمی با این شناسه پیدا نشد.")

        await message.reply_photo("https://i.imgur.com/HBYNljO.png", caption="🎬 به آرشیو خوش آمدید!")

        sent = []
        for f in film["files"]:
            m = await message.reply_document(
                f["file_id"],
                caption=f["caption"],
                reply_markup=build_buttons(f["_id"], f["views"], f["downloads"], f["shares"]),
                disable_notification=in_silent()
            )
            sent.append(m)

        warn = await message.reply("⏳ فایل‌ها بعد از ۳۰ ثانیه حذف می‌شوند.")
        sent.append(warn)

        await asyncio.sleep(30)
        for msg in sent:
            await msg.delete()

    else:
        await message.reply("برای دریافت فیلم، روی لینک داخل کانال کلیک کنید.")

# ========== آپلود توسط ادمین ==========
@app.on_message(filters.document & filters.user(ADMIN_IDS))
async def upload_file(client, message: Message):
    upload_cache[message.from_user.id] = {"step": "await_id", "file_id": message.document.file_id}
    await message.reply("📌 لطفاً شناسه فیلم را وارد کنید:")

@app.on_message(filters.text & filters.user(ADMIN_IDS))
async def upload_steps(client, message: Message):
    uid = message.from_user.id
    if uid not in upload_cache:
        return

    data = upload_cache[uid]

    if data["step"] == "await_id":
        data["film_id"] = message.text.strip()
        data["step"] = "await_caption"
        await message.reply("📝 کپشن فایل را وارد کنید:")

    elif data["step"] == "await_caption":
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

        await message.reply("✅ فایل ذخیره شد. فایل دیگری هم هست؟", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ بله", callback_data="upload_more")],
            [InlineKeyboardButton("❌ خیر", callback_data=f"done_{data['film_id']}")]
        ]))
        del upload_cache[uid]

# ========== دکمه‌ها ==========
@app.on_callback_query()
async def callbacks(client, query: CallbackQuery):
    data = query.data
    uid = query.from_user.id

    if data == "check_sub":
        if await is_subscribed(uid):
            await query.message.edit("✅ عضویت تأیید شد. لطفاً دوباره /start بزنید.")
        else:
            await query.answer("❗ هنوز عضو نیستید.", show_alert=True)

    elif data.startswith("done_"):
        fid = data.split("_")[1]
        link = f"https://t.me/BoxOfficeUploaderBot?start={fid}"
        qr = generate_qr(link)
        await query.message.reply_photo(qr, caption=f"📎 لینک اختصاصی:\n{link}")

    elif data.startswith("download_"):
        fid = data.split("_")[1]
        films_col.update_one({"files._id": fid}, {"$inc": {"files.$.downloads": 1}})
        await query.answer("⬇️ در حال دانلود...")

    elif data.startswith("stats_"):
        fid = data.split("_")[1]
        film = films_col.find_one({"files._id": fid})
        if film:
            for f in film["files"]:
                if f["_id"] == fid:
                    stats = f"👁 {f['views']} | 📥 {f['downloads']} | 🔁 {f['shares']}"
                    await query.answer(stats, show_alert=True)

    elif data == "upload_more":
        await query.message.reply("📤 فایل بعدی را ارسال کنید.")

# ========== تست Ping ==========
@app.on_message(filters.command("ping"))
async def ping(client, message):
    await message.reply("pong 🏓")

# ========== اجرای امن ربات ==========
async def start_bot():
    while True:
        try:
            logging.info("📦 اجرای ربات در حال شروع است...")
            await app.start()
            logging.info("✅ ربات با موفقیت اجرا شد.")
            await idle()
            break
        except FloodWait as e:
            logging.warning(f"🕒 FloodWait: {e.value} ثانیه صبر...")
            await asyncio.sleep(e.value)
        except Exception as e:
            logging.exception("❌ خطای اجرای ربات:")
            await asyncio.sleep(10)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import nest_asyncio
    nest_asyncio.apply()
    keep_alive()
    asyncio.run(start_bot())
    @app.on_message(filters.command("ping"))
async def ping(client, message):
    print("📥 ping received")
    await message.reply("pong 🏓")

