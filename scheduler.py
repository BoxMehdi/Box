import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

def start_scheduler():
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    scheduler.start()

def schedule_post(app, film_id, file_id, caption, post_time, channel_username):
    async def post_file():
        await app.send_document(chat_id=channel_username, document=file_id, caption=caption)
    scheduler.add_job(post_file, "date", run_date=post_time)
