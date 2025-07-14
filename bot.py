from pyrogram import Client, filters
from config import API_ID, API_HASH, BOT_TOKEN
from handlers.start import start_handler
from handlers.upload import handle_upload
from handlers.subscription import recheck_subscription

app = Client("BoxOfficeUploaderBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ثبت هندلرها
app.add_handler(filters.command("start"), start_handler)
app.add_handler(filters.private & filters.document, handle_upload)
app.add_handler(filters.callback_query, recheck_subscription)
