from telegram.ext import Application
from app.config import settings
from app.db import init_db
from app.handlers import register
from app.admin import register_admin
from services.scheduler import install_scheduler

def main():
    if not settings.bot_token: raise SystemExit('BOT_TOKEN não configurado.')
    init_db()
    app = Application.builder().token(settings.bot_token).build()
    register(app); register_admin(app); install_scheduler(app)
    print('Lomadee Auto Offers Bot 2.0 iniciado.')
    app.run_polling(allowed_updates=None)

if __name__ == '__main__': main()
