import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from urllib.parse import quote_plus

# تنظیمات
API_ID = 26438691  # عدد صحیح
API_HASH = "b9a6835fa0eea6e9f8a87a320b3ab1ae"
BOT_TOKEN = "8031070707:AAGaymxEcuqKCWO0f-dyPK0OqvnCXtUw570"
ADMIN_IDS = [7872708405, 6867380442]

MONGO_USER = "BoxOffice"
MONGO_PASS = "136215"
MONGO_CLUSTER = "boxofficeuploaderbot.2howsv3.mongodb.net"

REQUIRED_CHANNELS = [
    "BoxOffice_Animation",
    "BoxOfficeMoviiie",
    "BoxOffice_Irani",
    "BoxOfficeGoftegu"
]

# اتصال به MongoDB
MONGO_PASS_ENCODED = quote_plus(MONGO_PASS)
MONGO_URI = f"mongodb+srv://{MONGO_USER}:{MONGO_PASS_ENCODED}@{MONGO_CLUSTER}/?retryWrites=true&w=majority&appName=BoxOfficeUploaderBot"
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["boxoffice_db"]
files_collection = db["files"]
user_joined_collection = db["user_joined"]

upload_data = {}

app = Client("boxoffice_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# چک عضویت
async def user_is_subscribed(client, user_id):
    for channel in REQUIRED_CHANNELS:
        try:
            member = await client.get_chat_member(channel, user_id)
            if member.status in ("left", "kicked"):
                return False
        except:
            return False
    return True

def get_subscribe_buttons():
    buttons = [[InlineKeyboardButton(f"عضویت در @{chan}", url=f"https://t.me/{chan}")] for chan in REQUIRED_CHANNELS]
    buttons.append([InlineKeyboardButton("✅ عضو شدم", callback_data="check_subscription")])
    return InlineKeyboardMarkup(buttons)

def get_more_files_buttons():
    buttons = [
        [
            InlineKeyboardButton("✅ بله، فایل بعدی دارم", callback_data="more_files_yes"),
            InlineKeyboardButton("❌ خیر، تمام شد", callback_data="more_files_no"),
        ]
    ]
    return InlineKeyboardMarkup(buttons)

@app.on_message(filters.private & filters.command("start"))
async def start_handler(client, message):
    user_id = message.from_user.id
    args = message.text.split()

    if len(args) == 2:
        film_id = args[1]

        if not await user_is_subscribed(client, user_id):
            await message.reply(
                "❗️ لطفاً ابتدا در همه کانال‌های زیر عضو شوید و سپس روی دکمه 'عضو شدم' بزنید:",
                reply_markup=get_subscribe_buttons()
            )
            return

        files = list(files_collection.find({"film_id": film_id}))
        if not files:
            await message.reply("❌ هیچ فایلی با این شناسه پیدا نشد.")
            return

        sent_messages = []
        for file in files:
            caption_text = f"{file['caption']} | کیفیت: {file['quality']}"
            sent = await client.send_video(message.chat.id, file['file_id'], caption=caption_text)
            sent_messages.append(sent)

        warning_msg = await message.reply("⚠️ توجه: فایل‌ها تا ۳۰ ثانیه دیگر حذف خواهند شد، لطفاً آنها را ذخیره کنید.")
        sent_messages.append(warning_msg)

        asyncio.create_task(delete_messages_after(client, sent_messages, 30))
        return

    await message.reply(
        "🎬 به ربات BoxOffice خوش آمدید!\n\n"
        "ابتدا باید در کانال‌های زیر عضو شوید:",
        reply_markup=get_subscribe_buttons()
    )

@app.on_callback_query(filters.regex("^check_subscription$"))
async def check_subscription(client, callback_query):
    user_id = callback_query.from_user.id

    if await user_is_subscribed(client, user_id):
        user_record = user_joined_collection.find_one({"user_id": user_id})

        if not user_record:
            await callback_query.answer("✅ عضویت شما تایید شد!", show_alert=True)
            await callback_query.message.edit(
                "🎉 تبریک! شما برای اولین بار عضو همه کانال‌ها شدید! 🎊\n\n"
                "از اینکه همراه ما هستید سپاسگزاریم. اکنون می‌توانید با استفاده از لینک‌های اختصاصی، فایل‌ها را دریافت کنید.\n\n"
                "🌟 اگر سوالی داشتید، ما همیشه اینجا هستیم!"
            )
            user_joined_collection.insert_one({"user_id": user_id})
        else:
            await callback_query.answer("✅ عضویت شما تایید شد!", show_alert=True)
            await callback_query.message.edit(
                "🎉 شما عضو همه کانال‌ها هستید.\n\n"
                "برای دریافت فایل روی لینک‌های اختصاصی کلیک کنید."
            )
    else:
        await callback_query.answer("❌ هنوز عضو همه کانال‌ها نیستید!", show_alert=True)
        await callback_query.message.edit(
            "❗️ لطفاً ابتدا در همه کانال‌های زیر عضو شوید و سپس روی دکمه 'عضو شدم' بزنید:",
            reply_markup=get_subscribe_buttons()
        )

@app.on_message(filters.private & filters.video)
async def video_handler(client, message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await message.reply("⚠️ فقط ادمین اجازه ارسال ویدیو را دارد.")
        return

    # اگر مرحله انتظار ویدیو بود
    if user_id in upload_data and upload_data[user_id].get("step") == "awaiting_video":
        upload_data[user_id]["video_file_id"] = message.video.file_id
        upload_data[user_id]["step"] = "awaiting_film_id"
        await message.reply("✅ ویدیو دریافت شد.\nلطفاً شناسه عددی فیلم را وارد کنید:")
    else:
        # اولین یا شروع جدید
        upload_data[user_id] = {"video_file_id": message.video.file_id, "step": "awaiting_film_id"}
        await message.reply("✅ ویدیو دریافت شد.\nلطفاً شناسه عددی فیلم را وارد کنید:")

@app.on_message(filters.private & filters.text)
async def text_handler(client, message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        return

    if user_id not in upload_data:
        return

    step = upload_data[user_id].get("step")
    text = message.text.strip()

    if step == "awaiting_film_id":
        upload_data[user_id]["film_id"] = text
        upload_data[user_id]["step"] = "awaiting_caption"
        await message.reply("✅ شناسه دریافت شد.\nلطفاً کپشن فیلم را ارسال کنید:")

    elif step == "awaiting_caption":
        upload_data[user_id]["caption"] = text
        upload_data[user_id]["step"] = "awaiting_quality"
        await message.reply("✅ کپشن دریافت شد.\nلطفاً کیفیت فیلم را وارد کنید (مثلاً 720p):")

    elif step == "awaiting_quality":
        upload_data[user_id]["quality"] = text

        data = upload_data[user_id]
        files_collection.insert_one({
            "film_id": data["film_id"],
            "caption": data["caption"],
            "quality": data["quality"],
            "file_id": data["video_file_id"]
        })

        await message.reply(
            "✅ فیلم با موفقیت ذخیره شد.\n"
            "آیا فایل بعدی این فیلم را هم می‌خواهید آپلود کنید؟",
            reply_markup=get_more_files_buttons()
        )
        upload_data[user_id]["step"] = "awaiting_more_files"

@app.on_callback_query(filters.regex("^more_files_yes$"))
async def more_files_yes(client, callback_query):
    user_id = callback_query.from_user.id
    if user_id not in ADMIN_IDS:
        await callback_query.answer("⚠️ فقط ادمین می‌تواند فایل آپلود کند!", show_alert=True)
        return

    upload_data[user_id] = {"step": "awaiting_video"}
    await callback_query.message.edit("لطفاً فایل ویدیویی بعدی را ارسال کنید:")

@app.on_callback_query(filters.regex("^more_files_no$"))
async def more_files_no(client, callback_query):
    user_id = callback_query.from_user.id
    if user_id not in ADMIN_IDS:
        await callback_query.answer("⚠️ فقط ادمین می‌تواند فایل آپلود کند!", show_alert=True)
        return

    # آماده کردن لینک کلی
    # گرفتن فیلم آیدی از آخرین آپلود (می‌تونید بهترش کنید با ذخیره film_id در upload_data)
    # چون upload_data اینجا پاک شده، از یکی از فایل‌های اخیر استفاده می‌کنیم:
    last_file = files_collection.find_one(sort=[("_id", -1)])
    if last_file:
        film_id = last_file.get("film_id")
    else:
        film_id = "unknown"

    link = f"https://t.me/BoxOfficeUploaderBot?start={film_id}"

    # حذف داده‌های موقت کاربر
    upload_data.pop(user_id, None)

    await callback_query.message.edit(
        f"✅ تمام فایل‌های فیلم با شناسه {film_id} با موفقیت ذخیره شد.\n"
        f"این لینک را در کانال‌هایتان برای دسترسی کاربران قرار دهید:\n\n"
        f"{link}"
    )

async def delete_messages_after(client, messages, delay=30):
    await asyncio.sleep(delay)
    for msg in messages:
        try:
            await msg.delete()
        except:
            pass

if __name__ == "__main__":
    app.run()
