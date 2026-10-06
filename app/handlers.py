import html
from telegram import ReplyKeyboardRemove, Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, CallbackQueryHandler, TypeHandler, ApplicationHandlerStop, filters
from app import db
from app.crypto import encrypt
from app.config import settings
from adapters.lomadee import LomadeeAdapter
from services.publisher import publish_one

APIKEY, EMAIL, AFFILIATE, CAMPAIGN = range(4)


async def global_subscription_guard(update, context):
    user = update.effective_user

    if not user:
        return

    # ADMINISTRADOR: acesso livre
    if user.id in settings.admin_ids:
        return

    # Cliente com assinatura ativa: acesso livre
    try:
        client = ensure_client(update)
        if db.has_active_subscription(client["id"]):
            return
    except Exception:
        pass

    text = ""
    if update.message and update.message.text:
        text = update.message.text.strip()

    command = text.split()[0].lower() if text.startswith("/") else ""

    # /start é sempre permitido para mostrar o menu completo
    if command == "/start":
        return

    # Assinatura é sempre permitida
    if text == "💳 Assinatura" or command in ("/assinar", "/assinatura"):
        return

    # Todo o restante fica restrito
    if update.effective_chat and update.effective_chat.type != "private":
        raise ApplicationHandlerStop

    if update.message:
        await update.message.reply_text(
            "🔒 <b>FUNÇÃO BLOQUEADA</b>\n\n"
            "Sua assinatura ainda não está ativa.\n\n"
            "💰 <b>R$ 15,00</b>\n"
            "📅 <b>30 dias</b>\n\n"
            "💳 Toque em <b>Assinatura</b> para liberar "
            "todas as funções.",
            parse_mode="HTML",
            reply_markup=menu()
        )

    raise ApplicationHandlerStop



def menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton('💳 Assinatura'), KeyboardButton('⚙️ Configurações')],
        [KeyboardButton('🔗 Conta Lomadee'), KeyboardButton('📢 Grupo')],
        [KeyboardButton('▶️ Ativar'), KeyboardButton('⏸️ Pausar')],
        [KeyboardButton('🧪 Testar'), KeyboardButton('📊 Status')],
    ], resize_keyboard=True)


def ensure_client(update):
    u = update.effective_user
    return db.upsert_client(u.id, u.full_name or u.username or str(u.id))

def is_admin_user(update):
    user = update.effective_user
    return bool(user and user.id in settings.admin_ids)


def client_has_access(update):
    if is_admin_user(update):
        return True
    c = ensure_client(update)
    return db.has_active_subscription(c["id"])


async def subscription_required(update):
    if client_has_access(update):
        return True

    if update.effective_chat and update.effective_chat.type != "private":
        try:
            await update.message.reply_text(
                "🔒 Este bot requer uma assinatura ativa. "
                "Acesse o privado do bot para assinar."
            )
        except Exception:
            pass
        return False

    await update.message.reply_text(
        "🔒 <b>ACESSO BLOQUEADO</b>\n\n"
        "Sua assinatura não está ativa.\n\n"
        "💳 Valor: <b>R$ 15,00</b>\n"
        "📅 Validade: <b>30 dias</b>\n\n"
        "Toque em <b>💳 Assinatura</b> para gerar seu PIX.",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("💳 Assinatura")]],
            resize_keyboard=True
        )
    )
    return False


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
    c = ensure_client(update)
    d = context.user_data

    affiliate_id = update.message.text.strip()
    if affiliate_id == '-':
        affiliate_id = ''

    db.save_affiliate(c['id'], {
        'email': d.get('email', ''),
        'affiliate_id': affiliate_id,
        'source_id': '',
        'api_key_enc': encrypt(d['api_key']),
        'campaign': '',
        'status': 'testing',
    })

    fresh = db.get_affiliate(c['id'])

    try:
        await LomadeeAdapter(fresh).test_connection()
        db.set_affiliate_status(c['id'], 'connected')

        await update.message.reply_text(
            '✅ <b>Lomadee conectada!</b>\n\n'
            '🏪 Vou buscar automaticamente todas as lojas disponíveis na sua conta Lomadee.\n\n'
            'Agora adicione o bot como administrador do seu grupo/canal e use /grupo lá.',
            parse_mode='HTML',
            reply_markup=menu()
        )

    except Exception as e:
        db.set_affiliate_status(c['id'], 'error', str(e))

        await update.message.reply_text(
            f'⚠️ A chave foi salva, mas o teste falhou:\n'
            f'<code>{str(e)[:500]}</code>\n\n'
            f'Confira os escopos da API Key, principalmente brands:read.',
            parse_mode='HTML',
            reply_markup=menu()
        )

    context.user_data.clear()
    return ConversationHandler.END

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
    fresh = db.get_affiliate(c['id'])
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
    chat = update.effective_chat

    if chat.type == "private":
        await update.message.reply_text(
            "📢 O comando /grupo deve ser usado dentro do grupo/canal que você quer cadastrar."
        )
        return

    c = ensure_client(update)
    db.set_chat(c["id"], chat.id)

    # Remove o teclado administrativo antigo do grupo.
    try:
        msg = await update.message.reply_text(
            "✅ Grupo cadastrado. O painel administrativo fica somente no privado.",
            reply_markup=ReplyKeyboardRemove()
        )

        # Apaga a mensagem de confirmação para manter o grupo limpo.
        try:
            await msg.delete()
        except Exception:
            pass

    except Exception:
        pass

    # Envia a confirmação somente no privado.
    try:
        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text=(
                f"✅ Grupo/canal cadastrado: <b>{chat.title or chat.id}</b>\n\n"
                "O painel administrativo fica somente no privado."
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass


async def activate(update, context):
    if update.effective_chat.type != "private":
        return

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
    if update.effective_chat.type != "private":
        return

    c = ensure_client(update); db.set_active(c['id'], False)
    await update.message.reply_text('⏸️ Automação pausada.', reply_markup=menu())

async def status(update, context):
    if update.effective_chat.type != "private":
        return

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
    if update.effective_chat.type != "private":
        return

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


async def config_menu(update, context):
    if update.effective_chat.type != "private":
        return

    c = ensure_client(update)
    cfg = db.get_client_config(c["id"])

    popular = "✅ ATIVADO" if cfg["popular_enabled"] else "❌ DESATIVADO"

    lojas = (
        "Todas"
        if not cfg["stores"]
        else f"{len(cfg['stores'])} selecionada(s)"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"⏱️ Intervalo: {cfg['interval_minutes']} min",
                callback_data="cfg_interval"
            )
        ],
        [
            InlineKeyboardButton(
                f"🏪 Lojas: {lojas}",
                callback_data="cfg_stores"
            )
        ],
        [
            InlineKeyboardButton(
                f"📢 Publicações por dia: {c['daily_limit'] if c['daily_limit'] else '♾️'}",
                callback_data="cfg_daily"
            )
        ],
        [
            InlineKeyboardButton(
                f"🔥 Produto popular: {popular}",
                callback_data="cfg_popular"
            )
        ],
        [
            InlineKeyboardButton(
                "📢 Grupo",
                callback_data="cfg_group"
            )
        ],
    ])

    await update.message.reply_text(
        "⚙️ <b>CONFIGURAÇÕES</b>\n\n"
        f"⏱️ Intervalo: <b>{cfg['interval_minutes']} minutos</b>\n"
        f"🏪 Lojas: <b>{lojas}</b>\n"
        f"🔥 Produto popular: <b>{popular}</b>\n"
        f"📢 Grupo: <b>{'Configurado' if c['chat_id'] else 'Não configurado'}</b>",
        parse_mode="HTML",
        reply_markup=keyboard
    )


async def config_callback(update, context):
    query = update.callback_query
    await query.answer()

    c = ensure_client(update)
    cfg = db.get_client_config(c["id"])
    data = query.data or ""

    if data == "cfg_interval":
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("15 min", callback_data="cfg_i:15"),
                InlineKeyboardButton("30 min", callback_data="cfg_i:30"),
            ],
            [
                InlineKeyboardButton("60 min", callback_data="cfg_i:60"),
                InlineKeyboardButton("120 min", callback_data="cfg_i:120"),
            ],
            [
                InlineKeyboardButton("⬅️ Voltar", callback_data="cfg_main")
            ]
        ])

        await query.edit_message_text(
            "⏱️ <b>INTERVALO</b>\n\n"
            "Escolha de quanto em quanto tempo o bot poderá publicar:",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        return

    if data.startswith("cfg_i:"):
        minutes = int(data.split(":", 1)[1])

        db.save_client_config(
            c["id"],
            interval_minutes=minutes
        )

        await query.answer(
            f"Intervalo alterado para {minutes} minutos."
        )

        await config_callback_main(query, c)
        return

    if data == "cfg_popular":
        new_value = not cfg["popular_enabled"]

        db.save_client_config(
            c["id"],
            popular_enabled=new_value
        )

        await query.answer(
            "Produto popular ativado."
            if new_value
            else "Produto popular desativado."
        )

        await config_callback_main(query, c)
        return

    if data == "cfg_group":
        await query.edit_message_text(
            "📢 <b>GRUPO DE PUBLICAÇÃO</b>\n\n"
            "O grupo atual é definido pelo comando <b>/grupo</b>.\n\n"
            "Adicione o bot ao grupo e envie <b>/grupo</b> "
            "lá dentro para registrar esse grupo.",
            parse_mode="HTML"
        )
        return

    if data == "cfg_stores":
        await show_store_page(query, c, 1)
        return

    if data.startswith("cfg_sp:"):
        page = int(data.split(":", 1)[1])
        await show_store_page(query, c, page)
        return

    if data == "cfg_sa":
        db.save_client_config(
            c["id"],
            stores=[]
        )

        await query.answer("Todas as lojas selecionadas.")
        await show_store_page(query, c, 1)
        return

    if data.startswith("cfg_st:"):
        parts = data.split(":", 2)

        # Formato novo: cfg_st:PAGINA:ID
        if len(parts) == 3:
            try:
                page = int(parts[1])
            except ValueError:
                page = 1
            brand_id = parts[2]
        else:
            # Compatibilidade com botões antigos: cfg_st:ID
            brand_id = data.split(":", 1)[1]

            # Descobre a página atual pelo botão "X/Y"
            page = 1
            try:
                markup = query.message.reply_markup
                for row in markup.inline_keyboard:
                    for btn in row:
                        text = getattr(btn, "text", "") or ""
                        m = re.match(r"^(\d+)/(\d+)$", text.strip())
                        if m:
                            page = int(m.group(1))
                            break
                    else:
                        continue
                    break
            except Exception:
                page = 1

        current = db.get_client_config(c["id"])
        selected = list(current["stores"])

        if not selected:
            # Ao escolher uma loja partindo de "Todas",
            # passa a trabalhar com seleção específica.
            selected = [brand_id]
        elif brand_id in selected:
            selected.remove(brand_id)
        else:
            selected.append(brand_id)

        db.save_client_config(
            c["id"],
            stores=selected
        )

        await query.answer("Lojas atualizadas.")
        await show_store_page(query, c, page)
        return
    if data == "cfg_daily":
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("5 publicações", callback_data="cfg_d:5"),
                InlineKeyboardButton("10 publicações", callback_data="cfg_d:10"),
            ],
            [
                InlineKeyboardButton("12 publicações", callback_data="cfg_d:12"),
                InlineKeyboardButton("20 publicações", callback_data="cfg_d:20"),
            ],
            [
                InlineKeyboardButton("30 publicações", callback_data="cfg_d:30"),
                InlineKeyboardButton("50 publicações", callback_data="cfg_d:50"),
            ],
            [
                InlineKeyboardButton("100 publicações", callback_data="cfg_d:100"),
            ],
            [
                InlineKeyboardButton("♾️ Sem limite", callback_data="cfg_d:0"),
            ],
            [
                InlineKeyboardButton("⬅️ Voltar", callback_data="cfg_main")
            ]
        ])

        await query.edit_message_text(
            "📢 <b>PUBLICAÇÕES POR DIA</b>\n\n"
            "Escolha quantas ofertas o bot poderá publicar por dia.\n\n"
            "♾️ <b>Sem limite</b> = publica conforme o intervalo configurado.",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        return

    if data.startswith("cfg_d:"):
        try:
            limit = int(data.split(":", 1)[1])
        except Exception:
            limit = 12

        if limit not in (0, 5, 10, 12, 20, 30, 50, 100):
            limit = 12

        db.set_daily_limit(c["id"], limit)

        texto = "♾️ sem limite" if limit == 0 else f"{limit} publicações por dia"

        await query.answer("Limite atualizado.")
        await query.edit_message_text(
            f"✅ <b>PUBLICAÇÕES ATUALIZADAS</b>\n\n"
            f"📢 Limite diário: <b>{texto}</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Voltar às configurações",
                        callback_data="cfg_main"
                    )
                ]
            ])
        )
        return

    if data == "cfg_main":
        await config_callback_main(query, c)
        return


async def config_callback_main(query, c):
    cfg = db.get_client_config(c["id"])

    popular = (
        "✅ ATIVADO"
        if cfg["popular_enabled"]
        else "❌ DESATIVADO"
    )

    lojas = (
        "Todas"
        if not cfg["stores"]
        else f"{len(cfg['stores'])} selecionada(s)"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"⏱️ Intervalo: {cfg['interval_minutes']} min",
                callback_data="cfg_interval"
            )
        ],
        [
            InlineKeyboardButton(
                f"🏪 Lojas: {lojas}",
                callback_data="cfg_stores"
            )
        ],
        [
            InlineKeyboardButton(
                f"🔥 Produto popular: {popular}",
                callback_data="cfg_popular"
            )
        ],
        [
            InlineKeyboardButton(
                "📢 Grupo",
                callback_data="cfg_group"
            )
        ],
    ])

    await query.edit_message_text(
        "⚙️ <b>CONFIGURAÇÕES</b>\n\n"
        f"⏱️ Intervalo: <b>{cfg['interval_minutes']} minutos</b>\n"
        f"🏪 Lojas: <b>{lojas}</b>\n"
        f"🔥 Produto popular: <b>{popular}</b>\n"
        f"📢 Grupo: <b>{'Configurado' if c['chat_id'] else 'Não configurado'}</b>",
        parse_mode="HTML",
        reply_markup=keyboard
    )


_BRANDS_CACHE = {}
_BRANDS_CACHE_TIME = {}
_BRANDS_CACHE_TTL = 600

async def show_store_page(query, c, page=1):
    affiliate = db.get_affiliate(c["id"])

    if not affiliate or affiliate["status"] != "connected":
        await query.edit_message_text(
            "🔒 Conecte primeiro sua conta Lomadee."
        )
        return

    try:
        adapter = LomadeeAdapter(affiliate)

        import time
        cache_key = c["id"]
        now = time.time()

        if (
            cache_key not in _BRANDS_CACHE
            or now - _BRANDS_CACHE_TIME.get(cache_key, 0) > _BRANDS_CACHE_TTL
        ):
            _BRANDS_CACHE[cache_key] = await adapter.brands()
            _BRANDS_CACHE_TIME[cache_key] = now

        brands = _BRANDS_CACHE[cache_key]

    except Exception as e:
        await query.edit_message_text(
            f"❌ Não consegui carregar as lojas:\n{str(e)[:500]}"
        )
        return

    brands = [
        b for b in brands
        if isinstance(b, dict)
        and b.get("id")
        and b.get("name")
    ]

    per_page = 8
    total_pages = max(
        1,
        (len(brands) + per_page - 1) // per_page
    )

    page = max(1, min(page, total_pages))

    start = (page - 1) * per_page
    page_brands = brands[start:start + per_page]

    cfg = db.get_client_config(c["id"])
    selected = set(cfg["stores"])

    keyboard = []

    for brand in page_brands:
        bid = str(brand["id"])

        active = (
            not selected
            or bid in selected
        )

        name = str(brand["name"])[:25]

        keyboard.append([
            InlineKeyboardButton(
                ("✅ " if active else "⬜ ") + name,
                callback_data=f"cfg_st:{page}:{bid}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "🌐 TODAS",
            callback_data="cfg_sa"
        )
    ])

    nav = []

    if page > 1:
        nav.append(
            InlineKeyboardButton(
                "⬅️",
                callback_data=f"cfg_sp:{page-1}"
            )
        )

    nav.append(
        InlineKeyboardButton(
            f"{page}/{total_pages}",
            callback_data="cfg_stores"
        )
    )

    if page < total_pages:
        nav.append(
            InlineKeyboardButton(
                "➡️",
                callback_data=f"cfg_sp:{page+1}"
            )
        )

    keyboard.append(nav)

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Voltar",
            callback_data="cfg_main"
        )
    ])

    await query.edit_message_text(
        "🏪 <b>LOJAS</b>\n\n"
        "✅ = selecionada\n"
        "⬜ = não selecionada\n\n"
        "Quando nenhuma loja específica estiver marcada, "
        "o bot considera todas as lojas disponíveis na sua conta.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def button_router(update, context):
    t = (update.message.text or '').strip()

    if t == '⚙️ Configurações':
        await config_menu(update, context)
        return

    if t == '💳 Assinatura':
        await subscribe(update, context)
        return

    if t == '🔄 Verificar pagamento':
        await check_payment(update, context)
        return

    if t == '❌ Cancelar':
        await update.message.reply_text(
            'Operação cancelada.',
            reply_markup=menu() if client_has_access(update)
            else ReplyKeyboardMarkup(
                [[KeyboardButton('💳 Assinatura')]],
                resize_keyboard=True
            )
        )
        return

    if t == '🔗 Conta Lomadee':
        await lomadee(update, context)
        return

    if t == '📢 Grupo':
        await group(update, context)
        return

    if t == '▶️ Ativar':
        await activate(update, context)
        return

    if t == '⏸️ Pausar':
        await pause(update, context)
        return

    if t == '🧪 Testar':
        await test(update, context)
        return

    if t == '📊 Status':
        await status(update, context)
        return

def register(app):
    app.add_handler(
        CallbackQueryHandler(
            config_callback,
            pattern=r'^cfg_'
        )
    )

    # BLOQUEIO GLOBAL DE ASSINATURA
    app.add_handler(
        TypeHandler(Update, global_subscription_guard),
        group=-1
    )

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
    app.add_handler(CommandHandler('assinar', subscribe))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, button_router))

# ===== ASSINATURA / MERCADO PAGO =====

from services.payments import create_pix, get_payment, approved, DAYS

async def subscribe(update, context):
    if update.effective_chat.type != "private":
        return

    c = ensure_client(update)

    try:
        pix = await create_pix(
            c["telegram_id"],
            c["name"]
        )

        db.save_payment(
            c["id"],
            pix["payment_id"],
            15.00
        )

        qr = html.escape(pix["qr_code"] or "")

        await update.message.reply_text(
            "💳 <b>ASSINATURA MENSAL</b>\n\n"
            "💰 Valor: <b>R$ 15,00</b>\n"
            "📅 Validade: <b>30 dias</b>\n\n"
            "📲 <b>PIX COPIA E COLA</b>\n\n"
            f"<pre>{qr}</pre>\n\n"
            "⏳ <b>Pagamento automático</b>\n"
            "Assim que o Mercado Pago confirmar o pagamento, "
            "sua assinatura será liberada automaticamente.\n\n"
            "🚀 Você não precisa verificar manualmente.",
            parse_mode="HTML"
        )

        context.user_data["payment_id"] = pix["payment_id"]

    except Exception as e:
        await update.message.reply_text(
            f"❌ Não foi possível gerar o Pix:\n"
            f"<code>{html.escape(str(e)[:500])}</code>",
            parse_mode="HTML"
        )

async def check_payment(update, context):
    if update.effective_chat.type != "private":
        return

    payment_id = context.user_data.get("payment_id")

    if not payment_id:
        await update.message.reply_text(
            "❌ Você não possui um pagamento pendente."
        )
        return

    c = ensure_client(update)

    try:
        payment = await get_payment(payment_id)

        if approved(payment):
            expires = db.activate_subscription(
                c["id"],
                payment_id,
                DAYS
            )

            context.user_data.pop("payment_id", None)

            await update.message.reply_text(
                "✅ <b>PAGAMENTO CONFIRMADO!</b>\n\n"
                "🔓 Sua assinatura foi ativada.\n"
                "📅 Validade: <b>30 dias</b>\n\n"
                "Agora você já pode configurar o bot.",
                parse_mode="HTML",
                reply_markup=menu()
            )
            return

        status = payment.get("status", "pending")

        await update.message.reply_text(
            f"⏳ <b>Pagamento ainda não confirmado.</b>\n\n"
            f"Status: <code>{status}</code>\n\n"
            "Se você acabou de pagar, aguarde alguns segundos e "
            "toque novamente em <b>🔄 Verificar pagamento</b>.",
            parse_mode="HTML"
        )

    except Exception as e:
        await update.message.reply_text(
            f"❌ Erro ao consultar pagamento:\n<code>{str(e)[:500]}</code>",
            parse_mode="HTML"
        )
