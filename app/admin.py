from telegram.ext import CommandHandler
from app.config import settings
from app import db
from services.publisher import publish_one

def is_admin(update):
    return update.effective_user and update.effective_user.id in settings.admin_ids

async def clients(update, context):
    if not is_admin(update): return
    rows = db.list_clients(); lines=['👥 CLIENTES']
    for r in rows:
        lines.append(f'#{r["id"]} {r["name"]} | {r["lomadee_status"] or "sem conta"} | {"ON" if r["active"] else "OFF"}')
    await update.message.reply_text('\n'.join(lines) if len(lines)>1 else 'Nenhum cliente.')

async def post_now(update, context):
    if not is_admin(update): return
    ok=0
    for r in db.clients_active():
        try: await publish_one(context.bot, r, settings.min_score); ok+=1
        except Exception as e: print(f'[admin] {e}')
    await update.message.reply_text(f'🚀 Publicação manual concluída: {ok} cliente(s).')

async def health(update, context):
    if not is_admin(update): return
    h=db.health(); await update.message.reply_text(f'❤️ Health\nClientes: {h[0]}\nOfertas: {h[1]}\nPosts: {h[2]}')

def register_admin(app):
    app.add_handler(CommandHandler('clientes', clients)); app.add_handler(CommandHandler('postar_agora', post_now)); app.add_handler(CommandHandler('health', health))
