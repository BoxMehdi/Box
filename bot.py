import asyncio
import logging
import uuid
from datetime import datetime
from pymongo import MongoClient, ReturnDocument
import certifi
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
    InlineQuery, InlineQueryResultArticle, InputTextMessageContent,
    ChatMemberUpdated
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

# --- تنظیمات ---
API_ID = 27145047
API_HASH = "9e9672f2f920f277daca3d53502e0b34"
BOT_TOKEN = "7780760854:AAHjrEt0cMC3VFPgXxCGEG40ut_zf3fGLMU"
BOT_USERNAME = "BoxUploaderBot"

MONGO_URI = "mongodb+srv://BoxOffice:136215@boxofficeuploaderbot.2howsv3.mongodb.net/?retryWrites=true&w=majority&appName=BoxOfficeUploaderBot"
DB_NAME = "BoxOfficeUploaderBot"
COLLECTION_NAME = "files"
UPLOAD_STATE_COLLECTION = "upload_states"

ADMIN_IDS = [7872708405, 6867380442]
REQUIRED_CHANNELS = ["@BoxOffice_Irani", "@BoxOfficeMoviiie", "@BoxOffice_Animation", "@BoxOfficeGoftegu"]

WELCOME_IMAGE_URL = "https://i.imgur.com/uZqKsRs.png"
THANKS_IMAGE_URL = "https://i.imgur.com/fAGPuXo.png"

WELCOME_MESSAGE = (
    '<b dir="rtl">🎬 به ربات باکس‌آفیس خوش آمدید!</b>\n\n'
    '<span dir="rtl">لطفاً ابتدا در کانال‌ها و گروه‌های زیر عضو شوید و سپس روی دکمه «✅ عضو شدم» کلیک کنید.</span>'
)

THANKS_MESSAGE = (
    '<b dir="rtl">🌟 ممنون که عضو شدید!</b>\n\n'
    '<span dir="rtl">حالا می‌توانید از ربات استفاده کنید.</span>'
)

DELETE_WARNING = '<span dir="rtl">⏳ فقط ۳۰ ثانیه فرصت دارید فایل‌ها را ذخیره کنید! پس از آن پیام‌ها حذف خواهند شد.</span>'

DELETE_DELAY_SECONDS = 30
SILENT_MODE_START = 22  # ساعت 22:00
SILENT_MODE_END = 10    # ساعت 10:00

# --- اتصال به دیتابیس ---
mongo_client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = mongo_client[DB_NAME]
films_col = db[COLLECTION_NAME]
upload_states_col = db[UPLOAD_STATE_COLLECTION]

# --- کلاینت ربات ---
app = Client("BoxUploaderBotSession", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- توابع کمکی ---
def in_silent_mode() -> bool:
    now_hour = datetime.now().hour
    if SILENT_MODE_START > SILENT_MODE_END:
        return now_hour >= SILENT_MODE_START or now_hour < SILENT_MODE_END
    else:
        return SILENT_MODE_START <= now_hour < SILENT_MODE_END

async def is_user_subscribed(user_id: int) -> bool:
    for ch in REQUIRED_CHANNELS:
        try:
            member = await app.get_chat_member(ch, user_id)
            if member.status in ("left", "kicked"):
                return False
        except Exception:
            return False
    return True

def membership_keyboard(film_id: str = None):
    buttons = [[
        InlineKeyboardButton(f"📢 عضویت در {ch}", url=f"https://t.me/{ch.lstrip('@')}")
    ] for ch in REQUIRED_CHANNELS]
    data = "check_membership" if film_id is None else f"check_{film_id}"
    buttons.append([InlineKeyboardButton("✅ عضو شدم", callback_data=data)])
    return InlineKeyboardMarkup(buttons)

def upload_more_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ بله", callback_data="upload_more_yes"),
            InlineKeyboardButton("❌ خیر", callback_data="upload_more_no")
        ]
    ])

async def send_welcome_with_membership_buttons(user_id: int, film_id: str = None):
    text = WELCOME_MESSAGE
    keyboard = membership_keyboard(film_id)
    try:
        if WELCOME_IMAGE_URL.strip():
            await app.send_photo(
                chat_id=user_id,
                photo=WELCOME_IMAGE_URL,
                caption=text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
                disable_notification=in_silent_mode()
            )
        else:
            await app.send_message(
                chat_id=user_id,
                text=text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
                disable_notification=in_silent_mode()
            )
    except Exception as e:
        logger.error(f"[Error] Failed to send welcome message with photo to user {user_id}: {e}")
        await app.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
            disable_notification=in_silent_mode()
        )

async def send_thanks_message(user_id: int):
    text = THANKS_MESSAGE
    try:
        if THANKS_IMAGE_URL.strip():
            msg = await app.send_photo(
                chat_id=user_id,
                photo=THANKS_IMAGE_URL,
                caption=text,
                parse_mode=ParseMode.HTML,
                disable_notification=in_silent_mode()
            )
        else:
            msg = await app.send_message(
                chat_id=user_id,
                text=text,
                parse_mode=ParseMode.HTML,
                disable_notification=in_silent_mode()
            )
        return msg
    except Exception as e:
        logger.error(f"[Error] Failed to send thanks message to user {user_id}: {e}")

async def delete_messages_later(messages, delay=DELETE_DELAY_SECONDS):
    await asyncio.sleep(delay)
    for msg in messages:
        try:
            await msg.delete()
        except Exception:
            pass

def make_file_caption(file_doc):
    # ساخت کپشن با آمار و لینک دانلود کلیک‌خور
    caption = (
        f"<b dir='rtl'>{file_doc.get('caption', '')}</b>\n\n"
        f"🎞 کیفیت: {file_doc.get('quality', '')}\n"
        f"👁 بازدیدها: {file_doc.get('views', 0)} | 📥 دانلودها: {file_doc.get('downloads', 0)} | 🔁 اشتراک‌گذاری‌ها: {file_doc.get('shares', 0)}\n"
        f"🔗 <a href='https://t.me/{BOT_USERNAME}?start={file_doc.get('film_id')}'>مشاهده و دانلود فیلم</a>"
    )
    return caption

# --- هندلرها ---

@app.on_message(filters.command("ping") & filters.private)
async def ping_handler(client, message):
    await message.reply("pong 🏓", disable_notification=in_silent_mode())

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user_id = message.from_user.id
    args = message.text.split()

    if len(args) == 2:
        film_id = args[1]

        # بررسی عضویت کاربر در کانال‌ها
        for ch in REQUIRED_CHANNELS:
            try:
                member = await client.get_chat_member(ch, user_id)
                if member.status in ("left", "kicked"):
                    raise Exception("Not member")
            except Exception:
                btns = [[
                    InlineKeyboardButton(f"📢 عضویت در @{ch.lstrip('@')}", url=f"https://t.me/{ch.lstrip('@')}")
                ] for ch in REQUIRED_CHANNELS]
                btns.append([InlineKeyboardButton("✅ عضو شدم", callback_data=f"check_{film_id}")])
                await message.reply(
                    "📛 برای دریافت فایل ابتدا عضو کانال‌های زیر شوید:",
                    reply_markup=InlineKeyboardMarkup(btns),
                    disable_notification=in_silent_mode()
                )
                return

        files = list(films_col.find({"film_id": film_id}))
        if not files:
            await message.reply("❌ فایلی برای این شناسه پیدا نشد.", disable_notification=in_silent_mode())
            return

        sent_msgs = []
        for file in files:
            # افزایش شمارنده بازدید
            films_col.update_one({"file_id": file["file_id"]}, {"$inc": {"views": 1}})

            cap = make_file_caption(file)
            btns = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📥 دانلود", callback_data=f"download_{file['file_id']}"),
                    InlineKeyboardButton("🔁 اشتراک‌گذاری", switch_inline_query=f"film_{file['film_id'][:30]}"),
                    InlineKeyboardButton("📊 آمار", callback_data=f"stats_{file['file_id']}")
                ]
            ])

            sent = await message.reply_video(file['file_id'], caption=cap, reply_markup=btns, disable_notification=in_silent_mode())
            sent_msgs.append(sent)

        warning_msg = await message.reply(DELETE_WARNING, disable_notification=in_silent_mode())
        sent_msgs.append(warning_msg)

        asyncio.create_task(delete_messages_later(sent_msgs, DELETE_DELAY_SECONDS))

    else:
        await send_welcome_with_membership_buttons(user_id)

@app.on_callback_query(filters.regex(r"^check(_.*)?$"))
async def check_membership_callback(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data
    film_id = None
    if data.startswith("check_") and data != "check_membership":
        film_id = data.split("_", 1)[1]

    not_joined = []
    for ch in REQUIRED_CHANNELS:
        try:
            member = await app.get_chat_member(ch, user_id)
            if member.status in ("left", "kicked"):
                not_joined.append(ch)
        except Exception:
            not_joined.append(ch)

    if not_joined:
        text = "❌ هنوز در کانال‌ها و گروه‌های زیر عضو نشده‌اید:\n"
        text += "\n".join(not_joined)
        text += "\n\nلطفاً ابتدا عضو شوید و سپس دوباره روی «✅ عضو شدم» کلیک کنید."
        await callback_query.answer(text, show_alert=True)
        await send_welcome_with_membership_buttons(user_id, film_id)
    else:
        await callback_query.answer("🎉 تبریک! شما عضو همه کانال‌ها و گروه‌ها هستید.", show_alert=True)
        try:
            if THANKS_IMAGE_URL.strip():
                await callback_query.message.edit_media(
                    media=await app.download_media(THANKS_IMAGE_URL)
                )
                await callback_query.message.edit_caption(THANKS_MESSAGE, parse_mode=ParseMode.HTML, reply_markup=None)
            else:
                await callback_query.message.edit_text(THANKS_MESSAGE, parse_mode=ParseMode.HTML, reply_markup=None)
        except Exception:
            await callback_query.message.edit_text(THANKS_MESSAGE, parse_mode=ParseMode.HTML, reply_markup=None)

@app.on_callback_query(filters.regex(r"^download_(.+)$"))
async def download_handler(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    file_id = callback_query.data.split("_", 1)[1]
    # افزایش شمارنده دانلود
    films_col.update_one({"file_id": file_id}, {"$inc": {"downloads": 1}})
    await client.send_video(user_id, file_id, disable_notification=in_silent_mode())
    await callback_query.answer("فایل در حال ارسال است...", show_alert=False)
    try:
        await callback_query.message.delete()
    except Exception:
        pass

@app.on_callback_query(filters.regex(r"^stats_(.+)$"))
async def stats_handler(client, callback_query: CallbackQuery):
    file_id = callback_query.data.split("_", 1)[1]
    film = films_col.find_one({"file_id": file_id})
    if not film:
        await callback_query.answer("❌ فایل پیدا نشد.", show_alert=True)
        return
    text = (
        f"📊 آمار فایل:\n\n"
        f"👁 بازدیدها: {film.get('views', 0)}\n"
        f"📥 دانلودها: {film.get('downloads', 0)}\n"
        f"🔁 اشتراک‌گذاری‌ها: {film.get('shares', 0)}"
    )
    await callback_query.answer(text, show_alert=True)

@app.on_inline_query()
async def inline_query_handler(client: Client, inline_query: InlineQuery):
    query = inline_query.query.strip()
    user_id = inline_query.from_user.id
    if not query:
        await inline_query.answer(
            results=[],
            cache_time=0,
            switch_pm_text="لطفاً شناسه فیلم را وارد کنید.",
            switch_pm_parameter="start"
        )
        return

    result = films_col.find_one_and_update(
        {"film_id": query},
        {"$inc": {"shares": 1}},
        return_document=ReturnDocument.AFTER
    )
    if not result:
        await inline_query.answer(
            results=[],
            cache_time=0,
            switch_pm_text="فیلم پیدا نشد.",
            switch_pm_parameter="start"
        )
        return

    caption = (
        f"<b dir='rtl'>{result.get('caption', 'بدون توضیحات')}</b>\n\n"
        f"🎞 کیفیت: {result.get('quality', 'نامشخص')}\n"
        f"🎬 شناسه فیلم: <code>{result.get('film_id')}</code>"
    )
    results = [
        InlineQueryResultArticle(
            title=f"فیلم: {result.get('film_id')} - کیفیت {result.get('quality')}",
            input_message_content=InputTextMessageContent(
                message_text=caption,
                parse_mode=ParseMode.HTML
            ),
            description="کلیک کن تا پیام فیلم ارسال بشه.",
            id=str(uuid.uuid4())
        )
    ]
    await inline_query.answer(results=results, cache_time=0)

@app.on_message(filters.command("upload") & filters.private & filters.user(ADMIN_IDS))
async def upload_start(client, message):
    await message.reply("📝 لطفاً نام فیلم (شناسه یکتا) را وارد کنید:")
    upload_states_col.update_one(
        {"admin_id": message.from_user.id},
        {"$set": {"step": "waiting_title", "files": [], "cover_sent": False}},
        upsert=True
    )
    logger.info(f"Upload started by admin {message.from_user.id}")

@app.on_message(filters.private & filters.user(ADMIN_IDS))
async def upload_handler(client, message):
    state = upload_states_col.find_one({"admin_id": message.from_user.id})
    if not state:
        await message.reply("🚫 هیچ آپلود فعالی یافت نشد. لطفاً ابتدا دستور /upload را ارسال کنید.")
        return

    step = state.get("step")
    logger.info(f"Admin {message.from_user.id} - Upload step: {step}")

    text = message.text.strip() if message.text else None

    if step == "waiting_title":
        if not text:
            await message.reply("❌ لطفاً فقط متن ارسال کنید برای نام فیلم (شناسه یکتا).")
            return
        upload_states_col.update_one(
            {"admin_id": message.from_user.id},
            {"$set": {"step": "waiting_caption", "title": text, "files": [], "cover_sent": False}}
        )
        await message.reply("🖋 لطفاً کپشن فیلم را ارسال کنید:")
        return

    if step == "waiting_caption":
        if not text:
            await message.reply("❌ لطفاً فقط متن ارسال کنید برای کپشن فیلم.")
            return
        upload_states_col.update_one(
            {"admin_id": message.from_user.id},
            {"$set": {"step": "waiting_quality", "caption": text}}
        )
        await message.reply("🎞 لطفاً کیفیت فیلم را وارد کنید (مثلاً: 720p):")
        return

    if step == "waiting_quality":
        if not text:
            await message.reply("❌ لطفاً فقط متن ارسال کنید برای کیفیت فیلم.")
            return
        upload_states_col.update_one(
            {"admin_id": message.from_user.id},
            {"$set": {"step": "waiting_file", "quality": text}}
        )
        await message.reply("📤 لطفاً فایل ویدیویی را ارسال کنید:")
        return

    if step == "waiting_file":
        file_id = None
        if message.video:
            file_id = message.video.file_id
        elif message.document and message.document.file_name and message.document.file_name.lower().endswith((".mp4", ".mkv", ".avi", ".mov", ".wmv")):
            file_id = message.document.file_id
        else:
            await message.reply("❌ لطفاً فقط فایل ویدیویی معتبر ارسال کنید.")
            return

        files = state.get("files", [])
        files.append({
            "film_id": state["title"],
            "file_id": file_id,
            "caption": state["caption"],
            "quality": state["quality"],
            "download_link": f"https://t.me/{BOT_USERNAME}?start={state['title']}",
            "views": 0,
            "downloads": 0,
            "shares": 0
        })

        upload_states_col.update_one(
            {"admin_id": message.from_user.id},
            {"$set": {"files": files}}
        )

        logger.info(f"Admin {message.from_user.id} uploaded file for film {state['title']} quality {state['quality']}")

        if not state.get("cover_sent", False):
            upload_states_col.update_one(
                {"admin_id": message.from_user.id},
                {"$set": {"step": "waiting_cover", "cover_sent": True}}
            )
            await message.reply("🖼 لطفاً تصویر کاور (بنر) فیلم را ارسال کنید:")
            return

        upload_states_col.update_one(
            {"admin_id": message.from_user.id},
            {"$set": {"step": "ask_more"}}
        )
        await message.reply("📂 آیا فایل ویدیویی دیگری برای این فیلم دارید؟", reply_markup=upload_more_keyboard())
        return

    if step == "waiting_cover":
        if message.photo:
            cover_file_id = message.photo.file_id
            upload_states_col.update_one(
                {"admin_id": message.from_user.id},
                {"$set": {"cover_file_id": cover_file_id}}
            )
            upload_states_col.update_one(
                {"admin_id": message.from_user.id},
                {"$set": {"step": "ask_more"}}
            )
            await message.reply("📂 آیا فایل ویدیویی دیگری برای این فیلم دارید؟", reply_markup=upload_more_keyboard())
        else:
            await message.reply("❌ لطفاً فقط تصویر کاور ارسال کنید.")
        return

    if step == "ask_more":
        await message.reply("📂 لطفاً با استفاده از دکمه‌ها انتخاب کنید آیا فایل دیگری برای این فیلم دارید یا خیر.")
        return

@app.on_callback_query(filters.regex("^upload_more_"))
async def upload_more_callback(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data
    state = upload_states_col.find_one({"admin_id": user_id})

    if not state:
        await callback_query.answer("❌ وضعیت آپلود پیدا نشد!", show_alert=True)
        return

    if data == "upload_more_yes":
        upload_states_col.update_one(
            {"admin_id": user_id},
            {"$set": {"step": "waiting_quality"}}
        )
        await callback_query.message.edit_text("🎞 لطفاً کیفیت فایل بعدی را وارد کنید (مثلاً: 720p):")
        await callback_query.answer("✅ لطفاً فایل بعدی را ارسال کنید.", show_alert=True)

    elif data == "upload_more_no":
        title = state["title"]
        cover_file_id = state.get("cover_file_id")
        files = state.get("files", [])

        # حذف فایل‌های قبلی با همین شناسه فیلم (برای آپدیت کامل)
        films_col.delete_many({"film_id": title})

        # ذخیره کاور همراه با هر فایل (بهینه)
        if cover_file_id:
            for f in files:
                f["cover_file_id"] = cover_file_id

        # ذخیره فایل‌ها
        if files:
            films_col.insert_many(files)

        upload_states_col.delete_one({"admin_id": user_id})

        link = f"https://t.me/{BOT_USERNAME}?start={title}"

        await callback_query.message.edit_text(
            f"<b dir='rtl'>✅ آپلود فیلم {title} با موفقیت انجام شد.</b>\n\n"
            f"<b dir='rtl'>🔗 لینک اختصاصی جهت استفاده در کانال:</b>\n"
            f"<code>{link}</code>",
            parse_mode=ParseMode.HTML
        )
        await callback_query.answer("✅ آپلود با موفقیت انجام شد.", show_alert=True)

WELCOME_NEW_MEMBER_MESSAGE = (
    '<b dir="rtl">🌟 سلام {first_name} عزیز!</b>\n\n'
    '<span dir="rtl">🎉 به کانال/گروه ما خوش آمدی!</span>\n\n'
    '<span dir="rtl">🆔 شناسه شما: <code>{user_id}</code></span>\n'
    '<span dir="rtl">امیدواریم از حضور در اینجا لذت ببری! 💫</span>'
)

@app.on_chat_member_updated()
async def welcome_new_member(client: Client, chat_member_update: ChatMemberUpdated):
    chat = chat_member_update.chat
    if chat.username not in [ch.lstrip('@') for ch in REQUIRED_CHANNELS]:
        return

    # چک کردن وضعیت قبلی و جدید عضو
    old_status = getattr(chat_member_update.old_chat_member, "status", None)
    new_status = getattr(chat_member_update.new_chat_member, "status", None)
    user = chat_member_update.new_chat_member.user

    if old_status in ("left", "kicked") and new_status in ("member", "administrator", "creator"):
        try:
            await client.send_message(
                chat_id=user.id,
                text=WELCOME_NEW_MEMBER_MESSAGE.format(
                    first_name=user.first_name or "کاربر",
                    user_id=user.id
                ),
                parse_mode=ParseMode.HTML,
                disable_notification=in_silent_mode()
            )
        except Exception as e:
            logger.error(f"خطا در ارسال پیام خوشامدگویی به کاربر {user.id}: {e}")

if __name__ == "__main__":
    logger.info("🤖 ربات BoxOfficeUploaderBot در حال اجراست...")
    app.run()
