from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
from app import db
from app.crypto import encrypt
from app.config import settings
from adapters.lomadee import LomadeeAdapter
from services.publisher import publish_one

APIKEY, EMAIL, AFFILIATE, CAMPAIGN = range(4)


def menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton('🔗 Conta Lomadee'), KeyboardButton('📢 Grupo')],
        [KeyboardButton('▶️ Ativar'), KeyboardButton('⏸️ Pausar')],
        [KeyboardButton('🧪 Testar'), KeyboardButton('📊 Status')],
    ], resize_keyboard=True)


def ensure_client(update):
    u = update.effective_user
    return db.upsert_client(u.id, u.full_name or u.username or str(u.id))

async def start(update, context):
    ensure_client(update)
    await update.message.reply_text(
        '🤖 <b>Lomadee Auto Offers</b>\n\n'
        'Eu busco ofertas, preparo o anúncio e publico automaticamente no seu grupo.\n\n'
        'Comece em <b>🔗 Conta Lomadee</b>.',
        parse_mode='HTML', reply_markup=menu())

async def lomadee(update, context):
    ensure_client(update)
    await update.message.reply_text('🔐 <b>1/4</b> — Cole sua <b>API Key da Lomadee</b>.\n\nEla fica criptografada no servidor. Não envie sua senha da Lomadee.', parse_mode='HTML')
    return APIKEY

async def api_key(update, context):
    key = update.message.text.strip()
    if not key or len(key) < 10:
        await update.message.reply_text('❌ Essa chave parece inválida. Cole a API Key completa.')
        return APIKEY
    context.user_data['api_key'] = key
    await update.message.reply_text('🔐 <b>2/4</b> — E-mail da sua conta Lomadee (opcional).\nEnvie - para pular.', parse_mode='HTML')
    return EMAIL

async def email(update, context):
    context.user_data['email'] = '' if update.message.text.strip() == '-' else update.message.text.strip()
    await update.message.reply_text('🔐 <b>3/4</b> — ID/código de afiliado, se sua conta fornecer um.\nEnvie - se não souber.', parse_mode='HTML')
    return AFFILIATE

async def affiliate(update, context):
    context.user_data['affiliate_id'] = '' if update.message.text.strip() == '-' else update.message.text.strip()
    await update.message.reply_text('🏪 <b>4/4</b> — Loja/campanha para priorizar.\nDigite <b>shopee</b> ou - para deixar automático.', parse_mode='HTML')
    return CAMPAIGN

async def campaign(update, context):
    c = ensure_client(update)
    d = context.user_data
    campaign = update.message.text.strip()
    if campaign == '-': campaign = ''
    db.save_affiliate(c['id'], {
        'email': d.get('email',''),
        'affiliate_id': d.get('affiliate_id',''),
        'source_id': '',
        'api_key_enc': encrypt(d['api_key']),
        'campaign': campaign,
        'status': 'testing',
    })
    # Validate immediately with brands:read. This avoids saving a broken setup as active.
    fresh = db.get_client(update.effective_user.id)
    try:
        await LomadeeAdapter(fresh | {}).test_connection() if False else None
        # sqlite3.Row cannot be merged; use fresh directly.
        await LomadeeAdapter(fresh).test_connection()
        db.set_affiliate_status(c['id'], 'connected')
        await update.message.reply_text('✅ <b>Lomadee conectada!</b>\n\nAgora adicione o bot como administrador do seu grupo/canal e use /grupo lá.', parse_mode='HTML', reply_markup=menu())
    except Exception as e:
        db.set_affiliate_status(c['id'], 'error', str(e))
        await update.message.reply_text(f'⚠️ A chave foi salva, mas o teste falhou:\n<code>{str(e)[:500]}</code>\n\nConfira os escopos da API Key, principalmente brands:read.', parse_mode='HTML', reply_markup=menu())
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update, context):
    context.user_data.clear()
    await update.message.reply_text('Cadastro cancelado.', reply_markup=menu())
    return ConversationHandler.END

async def group(update, context):
    if update.effective_chat.type not in ('group','supergroup','channel'):
        await update.message.reply_text('Use /grupo dentro do grupo/canal onde o bot vai publicar.')
        return
    c = ensure_client(update)
    db.set_chat(c['id'], update.effective_chat.id)
    await update.message.reply_text(f'✅ Grupo/canal cadastrado: {update.effective_chat.title or update.effective_chat.id}\n\nAgora use /ativar.', reply_markup=menu())

async def activate(update, context):
    c = ensure_client(update)
    a = db.get_affiliate(c['id'])
    if not a or a['status'] != 'connected':
        await update.message.reply_text('❌ Primeiro conecte sua conta Lomadee em 🔗 Conta Lomadee.')
        return
    if not c['chat_id']:
        await update.message.reply_text('❌ Primeiro registre o grupo usando /grupo dentro dele.')
        return
    db.set_active(c['id'], True)
    await update.message.reply_text('▶️ Automação ativada. Vou publicar automaticamente no grupo cadastrado.', reply_markup=menu())

async def pause(update, context):
    c = ensure_client(update); db.set_active(c['id'], False)
    await update.message.reply_text('⏸️ Automação pausada.', reply_markup=menu())

async def status(update, context):
    c = ensure_client(update); a = db.get_affiliate(c['id'])
    if a:
        conta = {'connected':'🟢 conectada','testing':'🟡 testando','error':'🔴 erro'}.get(a['status'], a['status'])
        erro = f'\nErro: {a["last_error"][:180]}' if a['last_error'] else ''
    else:
        conta = '⚪ não cadastrada'; erro = ''
    await update.message.reply_text(
        f'📊 <b>SEU STATUS</b>\n\n'
        f'Lomadee: {conta}\n'
        f'Grupo: {"✅ cadastrado" if c["chat_id"] else "❌ não cadastrado"}\n'
        f'Automação: {"🟢 ativa" if c["active"] else "🔴 pausada"}\n'
        f'Publicações hoje: {db.count_posts_today(c["id"])}/{c["daily_limit"]}' + erro,
        parse_mode='HTML')

async def test(update, context):
    c = ensure_client(update)
    try:
        await publish_one(context.bot, c, settings.min_score)
        await update.message.reply_text('✅ Oferta publicada com sucesso.')
    except Exception as e:
        await update.message.reply_text(f'❌ Não foi possível publicar:\n{str(e)[:800]}')

async def referral(update, context):
    await update.message.reply_text(settings.owner_referral_url or 'O administrador ainda não configurou o link de indicação da Lomadee.')

async def help_cmd(update, context):
    await update.message.reply_text('/lomadee — conectar sua API Key\n/grupo — registrar o grupo atual\n/ativar — iniciar automático\n/pausar — parar\n/teste — publicar uma oferta\n/status — ver situação\n/indicacao — link de indicação\n/ajuda — ajuda')

async def button_router(update, context):
    t = update.message.text
    if t == '📢 Grupo': return await update.message.reply_text('Adicione o bot como administrador do grupo/canal e envie /grupo dentro dele.')
    if t == '▶️ Ativar': return await activate(update, context)
    if t == '⏸️ Pausar': return await pause(update, context)
    if t == '🧪 Testar': return await test(update, context)
    if t == '📊 Status': return await status(update, context)

def register(app):
    conv = ConversationHandler(
        entry_points=[CommandHandler('lomadee', lomadee), MessageHandler(filters.Regex(r'^🔗 Conta Lomadee$'), lomadee)],
        states={
            APIKEY:[MessageHandler(filters.TEXT & ~filters.COMMAND, api_key)],
            EMAIL:[MessageHandler(filters.TEXT & ~filters.COMMAND, email)],
            AFFILIATE:[MessageHandler(filters.TEXT & ~filters.COMMAND, affiliate)],
            CAMPAIGN:[MessageHandler(filters.TEXT & ~filters.COMMAND, campaign)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True,
    )
    app.add_handler(CommandHandler('start', start)); app.add_handler(conv)
    app.add_handler(CommandHandler('grupo', group)); app.add_handler(CommandHandler('ativar', activate)); app.add_handler(CommandHandler('pausar', pause))
    app.add_handler(CommandHandler('status', status)); app.add_handler(CommandHandler('teste', test)); app.add_handler(CommandHandler('indicacao', referral)); app.add_handler(CommandHandler('ajuda', help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, button_router))
