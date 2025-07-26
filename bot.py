import os
import asyncio
from datetime import datetime, time
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS").split(",")))
REQUIRED_CHANNELS = os.getenv("REQUIRED_CHANNELS").split(",")
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")
COLLECTION_NAME = os.getenv("COLLECTION_NAME")
UPLOAD_STATE_COLLECTION = os.getenv("UPLOAD_STATE_COLLECTION")
WELCOME_IMAGE_URL = os.getenv("WELCOME_IMAGE_URL")
THANKS_IMAGE_URL = os.getenv("THANKS_IMAGE_URL")
DELETE_DELAY_SECONDS = int(os.getenv("DELETE_DELAY_SECONDS"))
SILENT_MODE_START = int(os.getenv("SILENT_MODE_START"))
SILENT_MODE_END = int(os.getenv("SILENT_MODE_END"))

# اتصال به MongoDB
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[DB_NAME]
files_col = db[COLLECTION_NAME]
upload_states_col = db[UPLOAD_STATE_COLLECTION]

app = Client("BoxOfficeUploaderBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def is_silent_mode():
    now = datetime.now().time()
    start = time(SILENT_MODE_START)
    end = time(SILENT_MODE_END)
    if start < end:
        return start <= now < end
    else:
        return now >= start or now < end

async def check_channels_membership(user_id):
    for ch in REQUIRED_CHANNELS:
        try:
            member = await app.get_chat_member(ch, user_id)
            if member.status in ["kicked", "left"]:
                return False
        except Exception:
            return False
    return True

def get_join_channels_keyboard():
    buttons = [
        [InlineKeyboardButton(f"عضویت در {ch}", url=f"https://t.me/{ch.lstrip('@')}")]
        for ch in REQUIRED_CHANNELS
    ]
    buttons.append([InlineKeyboardButton("✅ من عضو شدم", callback_data="check_membership")])
    return InlineKeyboardMarkup(buttons)

@app.on_callback_query(filters.regex("check_membership"))
async def check_membership_callback(client, callback_query):
    user_id = callback_query.from_user.id
    if await check_channels_membership(user_id):
        await callback_query.message.edit_photo(
            photo=THANKS_IMAGE_URL,
            caption="🎉 تبریک! شما عضو همه کانال‌ها هستید. اکنون می‌توانید لینک فیلم‌ها را ارسال کنید.",
            reply_markup=None
        )
    else:
        await callback_query.answer("❌ شما هنوز عضو همه کانال‌ها نشده‌اید!", show_alert=True)

@app.on_message(filters.command("start"))
async def start_handler(client, message: Message):
    user_id = message.from_user.id
    args = message.text.split()
    if len(args) == 1:
        # استارت عادی
        await message.reply_photo(
            photo=WELCOME_IMAGE_URL,
            caption="👋 سلام! برای دریافت فیلم‌ها، ابتدا باید عضو کانال‌های زیر شوید:",
            reply_markup=get_join_channels_keyboard()
        )
    else:
        # استارت با آرگومان فیلم (مثلا /start film_id)
        film_id = args[1]
        if not await check_channels_membership(user_id):
            await message.reply_photo(
                photo=WELCOME_IMAGE_URL,
                caption="❗ برای مشاهده فیلم‌ها باید ابتدا عضو کانال‌ها شوید:",
                reply_markup=get_join_channels_keyboard()
            )
            return
        # نمایش فایل‌های فیلم
        files = list(files_col.find({"film_id": film_id}))
        if not files:
            await message.reply_text("❌ فیلمی با این شناسه پیدا نشد.")
            return
        msgs = []
        for f in files:
            caption = f.get("caption", "فیلم بدون توضیح")
            quality = f.get("quality", "کیفیت نامشخص")
            file_id = f.get("file_id")
            buttons = InlineKeyboardMarkup(
                [[InlineKeyboardButton("🎬 دانلود", callback_data=f"download_{file_id}")]]
            )
            m = await message.reply_video(
                file_id,
                caption=f"🎥 کیفیت: {quality}\n\n{caption}",
                reply_markup=buttons,
                disable_notification=is_silent_mode()
            )
            msgs.append(m)
        warn = await message.reply_text(
            f"⏳ این پیام‌ها و فیلم‌ها پس از {DELETE_DELAY_SECONDS} ثانیه حذف خواهند شد."
        )
        msgs.append(warn)
        await asyncio.sleep(DELETE_DELAY_SECONDS)
        for m in msgs:
            try:
                await m.delete()
            except:
                pass
        try:
            await message.delete()
        except:
            pass

@app.on_callback_query(filters.regex(r"download_(.+)"))
async def download_callback(client, callback_query):
    file_id = callback_query.data.split("_", 1)[1]
    try:
        await callback_query.message.reply_video(file_id, caption="🎬 این هم فیلم شما")
    except Exception as e:
        await callback_query.answer("❌ خطا در ارسال فیلم!", show_alert=True)

@app.on_message(filters.private & filters.user(ADMIN_IDS) & filters.media)
async def upload_handler(client, message: Message):
    state = upload_states_col.find_one({"admin_id": message.from_user.id})
    if not state:
        await message.reply_text("📝 لطفا ابتدا /upload را ارسال کنید.")
        return

    step = state.get("step", "")
    if step == "waiting_files":
        # ذخیره فایل‌ها در state
        files = state.get("files", [])
        files.append({
            "file_id": message.video.file_id if message.video else
                       message.document.file_id if message.document else None,
            "caption": message.caption or "",
            "quality": "",  # بعدا می‌پرسیم
        })
        upload_states_col.update_one(
            {"admin_id": message.from_user.id},
            {"$set": {"files": files}},
            upsert=True
        )
        await message.reply_text("✅ فایل دریافت شد. اگر فایل بیشتری دارید ارسال کنید یا /done را بزنید.")
    elif step == "waiting_title":
        await message.reply_text("❌ ابتدا /upload را ارسال کنید.")
    else:
        await message.reply_text("❌ وضعیت نامشخص. لطفا /upload را ارسال کنید.")

@app.on_message(filters.private & filters.user(ADMIN_IDS) & filters.command("upload"))
async def upload_start(client, message: Message):
    upload_states_col.update_one(
        {"admin_id": message.from_user.id},
        {"$set": {"step": "waiting_files", "files": [], "cover_sent": False}},
        upsert=True
    )
    await message.reply_text("📝 لطفا فایل‌های فیلم را ارسال کنید. پس از پایان ارسال، /done را ارسال کنید.")

@app.on_message(filters.private & filters.user(ADMIN_IDS) & filters.command("done"))
async def upload_done(client, message: Message):
    state = upload_states_col.find_one({"admin_id": message.from_user.id})
    if not state or state.get("step") != "waiting_files":
        await message.reply_text("❌ ابتدا با دستور /upload آپلود را شروع کنید.")
        return

    files = state.get("files", [])
    if not files:
        await message.reply_text("❌ هیچ فایلی دریافت نشده است.")
        return

    # ذخیره فایل‌ها در دیتابیس با شناسه منحصر بفرد فیلم
    film_id = str(datetime.now().timestamp()).replace('.', '')
    for f in files:
        record = {
            "film_id": film_id,
            "file_id": f["file_id"],
            "caption": f["caption"],
            "quality": f["quality"],
            "uploaded_by": message.from_user.id,
            "upload_date": datetime.utcnow()
        }
        files_col.insert_one(record)

    upload_states_col.delete_one({"admin_id": message.from_user.id})

    deep_link = f"https://t.me/{BOT_USERNAME}?start={film_id}"
    await message.reply_text(
        f"🎉 فایل‌ها با موفقیت ذخیره شدند.\nلینک اشتراک‌گذاری:\n{deep_link}"
    )

@app.on_message(filters.private & filters.user(ADMIN_IDS) & filters.command("cancel"))
async def upload_cancel(client, message: Message):
    upload_states_col.delete_one({"admin_id": message.from_user.id})
    await message.reply_text("❌ آپلود لغو شد.")

@app.on_message(filters.private & filters.user())
async def user_start_private(client, message: Message):
    if message.text and message.text.startswith("/start"):
        await start_handler(client, message)

print("🤖 ربات BoxOfficeUploaderBot در حال اجراست...")
app.run()
