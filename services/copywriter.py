import html
import hashlib
import json
import os
import re

import httpx
from dotenv import dotenv_values

ENV = dotenv_values("/home/ubuntu/LOMADEE-AUTOBOT/.env")

GEMINI_API_KEY = (
    ENV.get("GEMINI_API_KEY")
    or os.getenv("GEMINI_API_KEY")
    or ""
).strip()

GEMINI_MODEL = (
    ENV.get("GEMINI_MODEL")
    or os.getenv("GEMINI_MODEL")
    or "gemini-2.5-flash"
).strip()

GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)


def money(v):
    if v is None:
        return ''
    try:
        v = float(v)
        return (
            f'R$ {v:,.2f}'
            .replace(',', 'X')
            .replace('.', ',')
            .replace('X', '.')
        )
    except Exception:
        return str(v)


def product_kind(title):
    t = (title or '').lower()

    groups = [
        (['celular', 'smartphone', 'iphone', 'galaxy'],
         '📱 Uma ótima opção para quem procura tecnologia e praticidade.'),
        (['notebook', 'computador', 'pc', 'monitor', 'teclado', 'mouse'],
         '💻 Uma opção interessante para trabalho, estudo ou uso no dia a dia.'),
        (['tv', 'televisão', 'smart tv'],
         '📺 Uma boa opção para renovar o entretenimento de casa.'),
        (['fone', 'headset', 'earbuds', 'caixa de som', 'speaker'],
         '🎧 Uma opção para curtir músicas, vídeos e conteúdos favoritos.'),
        (['perfume', 'colônia', 'fragrância'],
         '🌸 Uma opção para quem gosta de perfumaria e cuidados pessoais.'),
        (['shampoo', 'condicionador', 'leave-in', 'balm', 'creme', 'hidratante', 'cosmético'],
         '✨ Uma opção para cuidados pessoais e beleza.'),
        (['whey', 'proteína', 'creatina', 'vitamina', 'magnésio', 'suplemento'],
         '💪 Uma opção para quem procura produtos de suplementação.'),
        (['brinquedo', 'boneca', 'carrinho', 'lego', 'jogo'],
         '🧸 Uma opção para presentear ou divertir a criançada.'),
        (['roupa', 'camisa', 'calça', 'vestido', 'tênis', 'sapato', 'sandália'],
         '👕 Uma opção para renovar o visual pagando menos.'),
        (['cozinha', 'panela', 'frigideira', 'liquidificador', 'air fryer'],
         '🍳 Uma opção prática para a cozinha e para o dia a dia.'),
        (['ferramenta', 'furadeira', 'parafusadeira', 'serra'],
         '🔧 Uma opção interessante para ferramentas e trabalhos em casa.'),
        (['livro', 'romance', 'literatura'],
         '📚 Uma opção para quem gosta de leitura ou procura um presente.'),
        (['cama', 'mesa', 'cadeira', 'sofá', 'decoração', 'almofada'],
         '🏠 Uma opção para deixar a casa mais confortável e bonita.'),
    ]

    for words, text in groups:
        if any(word in t for word in words):
            return text

    return '✨ Uma oferta que vale a pena conferir enquanto o preço estiver disponível.'


def build_caption(o):
    title = html.escape(str(o.title or 'Oferta')[:180])
    kind = product_kind(o.title)

    seed = hashlib.md5(title.encode('utf-8')).hexdigest()

    templates = [
        '🔥 ACHADO DO DIA!',
        '🚨 OFERTA ENCONTRADA!',
        '💥 PREÇO ESPECIAL!',
        '🛍️ OFERTA QUE VALE CONFERIR!',
        '⚡ OLHA ESSA OFERTA!',
        '🔥 OFERTA EM DESTAQUE!',
    ]

    index = int(seed[:8], 16) % len(templates)
    headline = templates[index]

    lines = [
        f'<b>{headline}</b>',
        '',
        f'🛍️ <b>{title}</b>',
        '',
        kind,
    ]

    if o.old_price and o.price and o.old_price > o.price:
        disc = (1 - (o.price / o.old_price)) * 100

        lines += [
            '',
            f'💰 De <s>{money(o.old_price)}</s> por <b>{money(o.price)}</b>',
            f'🏷️ <b>{disc:.0f}% OFF</b>',
        ]

    elif o.price:
        lines += [
            '',
            f'💰 <b>Por {money(o.price)}</b>',
        ]

    lines += [
        '',
        '⚡ Preço sujeito a alteração ou encerramento da oferta.',
        '',
        '👇 <b>Toque no botão abaixo para ver a oferta</b>',
    ]

    return '\n'.join(lines)


def _description(o):
    try:
        raw = json.loads(o.raw_json or '{}')
    except Exception:
        raw = {}

    if not isinstance(raw, dict):
        return ''

    description = (
        raw.get('description')
        or raw.get('shortDescription')
        or raw.get('summary')
        or ''
    )

    if isinstance(description, str):
        return re.sub(r'\s+', ' ', description).strip()[:700]

    return ''


def _clean_ai_text(text):
    if not text:
        return ''

    text = text.strip()

    # Remove cercas de Markdown caso o modelo envie.
    text = re.sub(r'^```(?:html)?\s*', '', text, flags=re.I)
    text = re.sub(r'\s*```$', '', text)

    # Mantém somente tags HTML aceitas pelo Telegram.
    allowed = {'b', 'strong', 'i', 'em', 'u', 's', 'strike', 'del', 'code'}

    def clean_tag(match):
        tag = match.group(0)
        name = re.match(r'</?\s*([a-zA-Z0-9]+)', tag)

        if not name:
            return ''

        tag_name = name.group(1).lower()

        if tag_name in allowed:
            return tag

        return ''

    text = re.sub(r'</?[^>]+>', clean_tag, text)

    return text[:3800].strip()


async def build_caption_ai(o):
    """
    Usa Gemini para melhorar o anúncio.
    Se a API falhar, retorna o texto tradicional.
    """

    fallback = build_caption(o)

    if not GEMINI_API_KEY:
        return fallback

    title = str(o.title or 'Oferta').strip()[:300]
    description = _description(o)

    current_price = money(o.price) if o.price else ''
    old_price = money(o.old_price) if o.old_price else ''

    discount = ''
    if o.old_price and o.price and o.old_price > o.price:
        discount = f'{((1 - o.price / o.old_price) * 100):.0f}%'

    prompt = f"""
Você é um redator especialista em ofertas para Telegram.

Crie um anúncio curto, chamativo e natural em português do Brasil.

DADOS REAIS DO PRODUTO:
Nome: {title}
Preço atual: {current_price}
Preço anterior: {old_price}
Desconto calculado: {discount}
Descrição real: {description}

REGRAS IMPORTANTES:
- NÃO invente características, benefícios, avaliações ou informações.
- Use somente os dados fornecidos.
- Preserve exatamente o nome e os preços.
- Se não houver descrição, não invente uma.
- Não diga que é "o mais vendido" ou "o melhor" sem essa informação.
- Use emojis com moderação.
- Deixe o texto fácil de ler no Telegram.
- Tenha uma chamada inicial atraente.
- Destaque o preço.
- Termine indicando que a pessoa pode conferir a oferta no botão abaixo.
- Não coloque URL.
- Não coloque código Markdown.
- Pode usar somente as tags HTML <b>, <i> e <s>.
- Retorne SOMENTE o texto do anúncio.

O anúncio deve ficar aproximadamente entre 400 e 900 caracteres.
"""

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.8,
            "maxOutputTokens": 500
        }
    }

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
    }

    try:
        # Tenta o modelo principal e depois modelos alternativos.
        models = [
            GEMINI_MODEL,
            "gemini-3.7-flash",
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-3.5-flash-lite",
            "gemini-2.5-flash",
        ]

        # Remove duplicados mantendo a ordem.
        models = list(dict.fromkeys(models))

        async with httpx.AsyncClient(timeout=20) as client:

            for model in models:
                url = (
                    "https://generativelanguage.googleapis.com/"
                    f"v1beta/models/{model}:generateContent"
                )

                print(f"[gemini] Tentando modelo: {model}")

                try:
                    response = await client.post(
                        url,
                        headers=headers,
                        json=payload
                    )
                except Exception as model_error:
                    print(
                        f"[gemini] erro no modelo {model}: "
                        f"{model_error}"
                    )
                    continue

                if response.status_code == 200:
                    data = response.json()

                    candidates = data.get("candidates") or []

                    if not candidates:
                        print(
                            f"[gemini] {model}: sem candidates"
                        )
                        continue

                    parts = (
                        candidates[0]
                        .get("content", {})
                        .get("parts", [])
                    )

                    text = ''.join(
                        str(part.get("text", ""))
                        for part in parts
                        if isinstance(part, dict)
                    ).strip()

                    text = _clean_ai_text(text)

                    if len(text) >= 80:
                        print(
                            f"[gemini] Texto gerado com sucesso "
                            f"usando {model}."
                        )
                        return text

                    print(
                        f"[gemini] {model}: resposta muito curta"
                    )
                    continue

                print(
                    f"[gemini] {model} HTTP "
                    f"{response.status_code}: "
                    f"{response.text[:300]}"
                )

                # 503/429/5xx: tenta automaticamente o próximo.
                continue

        print("[gemini] Nenhum modelo conseguiu gerar o texto.")
        return fallback

    except Exception as e:
        print(f"[gemini] erro: {e}")
        return fallback
