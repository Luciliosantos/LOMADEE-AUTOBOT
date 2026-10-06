import json

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app import db
from adapters.lomadee import LomadeeAdapter
from services.scoring import score_offer
from services.copywriter import build_caption_ai


def _brand_values(value):
    """
    Extrai IDs/nomes/slugs de marcas de forma tolerante
    aos diferentes formatos retornados pela Lomadee.
    """
    values = set()

    def walk(obj, parent_key=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                key = str(k).lower()

                if any(x in key for x in (
                    "brand", "merchant", "store", "loja"
                )):
                    if isinstance(v, str):
                        values.add(v.strip().lower())

                    elif isinstance(v, dict):
                        for kk in ("id", "name", "slug", "brandId"):
                            if v.get(kk) is not None:
                                values.add(
                                    str(v.get(kk)).strip().lower()
                                )

                    elif isinstance(v, list):
                        for item in v:
                            walk(item, key)

                if isinstance(v, (dict, list)):
                    walk(v, key)

        elif isinstance(obj, list):
            for item in obj:
                walk(item, parent_key)

        elif isinstance(obj, str) and parent_key:
            values.add(obj.strip().lower())

    walk(value)
    return values


def _matches_stores(offer, selected_stores, store_map=None):
    """
    Verifica a loja pelo domínio do produto.

    Os IDs selecionados no menu são IDs de brands da Lomadee.
    O produto, porém, não traz esse mesmo ID. A URL do produto
    contém o domínio da loja.
    """

    # Nenhuma loja selecionada = todas as lojas
    if not selected_stores:
        return True

    import json
    from urllib.parse import urlparse

    try:
        raw = json.loads(offer.raw_json or "{}")
    except Exception:
        raw = {}

    product_url = str(
        getattr(offer, "url", "")
        or raw.get("url", "")
        or ""
    ).strip().lower()

    if not product_url:
        return False

    try:
        hostname = urlparse(product_url).hostname or ""
    except Exception:
        hostname = ""

    hostname = hostname.lower().strip()
    hostname = hostname[4:] if hostname.startswith("www.") else hostname

    # O mapa é obtido da Lomadee e mantido em cache.
    # Se o produto tiver algum campo explícito de loja,
    # também tentamos utilizá-lo.
    candidates = []

    def collect(value):
        if isinstance(value, dict):
            for key in ("id", "brandId", "merchantId", "storeId"):
                if value.get(key):
                    candidates.append(str(value[key]))

            for key in ("name", "slug", "site", "domain"):
                if value.get(key):
                    candidates.append(str(value[key]).lower())

        elif isinstance(value, list):
            for item in value:
                collect(item)

        elif value is not None:
            candidates.append(str(value).lower())

    for key in ("brand", "merchant", "store", "loja"):
        if key in raw:
            collect(raw.get(key))

    # IDs antigos continuam sendo aceitos quando o produto fornecer um.
    selected = {str(x).lower() for x in selected_stores}

    if selected.intersection({x.lower() for x in candidates}):
        return True

    # O publisher pode receber um mapa de lojas criado pelo scheduler.
    store_map = getattr(offer, "_lomadee_store_map", None)

    if isinstance(store_map, dict):
        for store_id in selected_stores:
            store = store_map.get(str(store_id))
            if not isinstance(store, dict):
                continue

            site = str(store.get("site") or "").lower().strip()
            site = site[4:] if site.startswith("www.") else site

            slug = str(store.get("slug") or "").lower().strip()

            if site and (hostname == site or hostname.endswith("." + site)):
                return True

            if slug and slug in hostname:
                return True

    return False

def _popularity_bonus(offer):
    """
    Usa sinais de popularidade somente quando a API realmente
    fornecer esses campos.
    """
    try:
        raw = getattr(offer, "raw_json", "") or ""
        data = json.loads(raw) if isinstance(raw, str) else raw

        values = []

        def walk(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    key = str(k).lower()

                    if any(x in key for x in (
                        "sales",
                        "sold",
                        "orders",
                        "rating",
                        "reviews",
                        "reviewcount",
                        "popularity"
                    )):
                        try:
                            values.append(float(v))
                        except Exception:
                            pass

                    if isinstance(v, (dict, list)):
                        walk(v)

            elif isinstance(obj, list):
                for item in obj:
                    walk(item)

        walk(data)

        if not values:
            return 0

        # Pequeno bônus, sem deixar popularidade dominar o score.
        return min(15, max(0, int(max(values) / 10)))

    except Exception:
        return 0


async def fetch_best(
    adapter,
    min_score=55,
    client_id=None
):
    config = (
        db.get_client_config(client_id)
        if client_id is not None
        else {
            "stores": [],
            "popular_enabled": True
        }
    )

    offers = await adapter.products(50)

    # Mapa das lojas da Lomadee:
    # ID da loja -> dados contendo site, slug e nome.
    store_map = {}

    if config.get("stores"):
        try:
            brands = await adapter.brands()

            for brand in brands:
                if not isinstance(brand, dict):
                    continue

                brand_id = str(brand.get("id") or "").strip()

                if brand_id:
                    store_map[brand_id] = brand

            print(
                f"[publisher] mapa de lojas carregado: "
                f"{len(store_map)}"
            )

        except Exception as e:
            print(
                f"[publisher] erro ao carregar mapa de lojas: {e}"
            )


    filtered = []

    for o in offers:

        if not _matches_stores(
            o,
            config["stores"],
            store_map
        ):
            continue

        o.score = score_offer(o)

        if config["popular_enabled"]:
            o.score += _popularity_bonus(o)

        if o.score >= min_score:
            filtered.append(o)

    return sorted(
        filtered,
        key=lambda x: x.score,
        reverse=True
    )


async def publish_one(bot, client, min_score=55):

    if not client['chat_id']:
        raise RuntimeError(
            'Cliente ainda não cadastrou o grupo/canal.'
        )

    if db.count_posts_today(client['id']) >= client['daily_limit']:
        raise RuntimeError(
            'Limite diário atingido.'
        )

    affiliate = db.get_affiliate(client['id'])

    if not affiliate or affiliate['status'] != 'connected':
        raise RuntimeError(
            'Conta Lomadee não está conectada.'
        )

    adapter = LomadeeAdapter(affiliate)

    candidates = await fetch_best(
        adapter,
        min_score,
        client['id']
    )

    for o in candidates:

        saved = db.save_offer(o)

        if db.was_posted(
            client['id'],
            saved['id']
        ):
            continue

        if not o.url:
            continue

        aff = await adapter.affiliate_url(o.url)

        if not aff:
            continue

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    '🛒 VER OFERTA',
                    url=aff
                )
            ]
        ])

        caption = await build_caption_ai(o)

        if o.image_url:

            msg = await bot.send_photo(
                chat_id=client['chat_id'],
                photo=o.image_url,
                caption=caption,
                parse_mode='HTML',
                reply_markup=keyboard
            )

        else:

            msg = await bot.send_message(
                chat_id=client['chat_id'],
                text=caption,
                parse_mode='HTML',
                reply_markup=keyboard,
                disable_web_page_preview=False
            )

        db.save_post(
            client['id'],
            saved['id'],
            aff,
            msg.message_id
        )

        return msg

    raise RuntimeError(
        'Nenhuma oferta nova disponível com pontuação suficiente.'
    )
