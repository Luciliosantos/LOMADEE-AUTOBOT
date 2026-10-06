from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from app import db
from adapters.lomadee import LomadeeAdapter
from services.scoring import score_offer
from services.copywriter import build_caption

async def fetch_best(adapter, min_score=55):
    offers = await adapter.products(50)
    for o in offers: o.score = score_offer(o)
    return sorted([o for o in offers if o.score >= min_score], key=lambda x:x.score, reverse=True)

async def publish_one(bot, client, min_score=55):
    if not client['chat_id']:
        raise RuntimeError('Cliente ainda não cadastrou o grupo/canal.')
    if db.count_posts_today(client['id']) >= client['daily_limit']:
        raise RuntimeError('Limite diário atingido.')
    adapter = LomadeeAdapter(client)
    candidates = await fetch_best(adapter, min_score)
    for o in candidates:
        saved = db.save_offer(o)
        if db.was_posted(client['id'], saved['id']): continue
        if not o.url: continue
        aff = await adapter.affiliate_url(o.url)
        if not aff: continue
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton('🛒 VER OFERTA', url=aff)]])
        caption = build_caption(o)
        if o.image_url:
            msg = await bot.send_photo(chat_id=client['chat_id'], photo=o.image_url, caption=caption, parse_mode='HTML', reply_markup=keyboard)
        else:
            msg = await bot.send_message(chat_id=client['chat_id'], text=caption, parse_mode='HTML', reply_markup=keyboard, disable_web_page_preview=False)
        db.save_post(client['id'], saved['id'], aff, msg.message_id)
        return msg
    raise RuntimeError('Nenhuma oferta nova disponível com pontuação suficiente.')
