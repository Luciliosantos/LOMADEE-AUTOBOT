from telegram.ext import Application
from app import db
from services.publisher import publish_one
from app.config import settings

async def scheduled_job(context):
    for client in db.clients_active():
        try:
            await publish_one(context.bot, client, settings.min_score)
        except Exception as e:
            print(f'[scheduler] cliente={client["id"]}: {e}')

def install_scheduler(app: Application):
    app.job_queue.run_repeating(scheduled_job, interval=max(5, settings.interval_minutes)*60, first=20)
