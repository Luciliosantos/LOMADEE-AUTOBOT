import html
import hashlib


def money(v):
    if v is None:
        return ''
    try:
        v = float(v)
        return f'R$ {v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    except Exception:
        return str(v)


def product_kind(title):
    t = (title or '').lower()

    groups = [
        (['celular', 'smartphone', 'iphone', 'galaxy'], '📱 Uma ótima opção para quem está procurando tecnologia e praticidade.'),
        (['notebook', 'computador', 'pc', 'monitor', 'teclado', 'mouse'], '💻 Uma opção interessante para trabalho, estudo ou uso no dia a dia.'),
        (['tv', 'televisão', 'smart tv'], '📺 Uma boa opção para renovar o entretenimento de casa.'),
        (['fone', 'headset', 'earbuds', 'caixa de som', 'speaker'], '🎧 Uma opção para curtir suas músicas, vídeos e conteúdos favoritos.'),
        (['perfume', 'colônia', 'fragrância'], '🌸 Uma opção para quem gosta de perfumaria e cuidados pessoais.'),
        (['shampoo', 'condicionador', 'leave-in', 'balm', 'creme', 'hidratante', 'cosmético'], '✨ Uma opção para cuidados pessoais e beleza.'),
        (['whey', 'proteína', 'creatina', 'vitamina', 'magnésio', 'suplemento'], '💪 Uma opção para quem procura produtos de suplementação.'),
        (['brinquedo', 'boneca', 'carrinho', 'lego', 'jogo'], '🧸 Uma opção para presentear ou divertir a criançada.'),
        (['roupa', 'camisa', 'calça', 'vestido', 'tênis', 'sapato', 'sandália'], '👕 Uma opção para renovar o visual pagando menos.'),
        (['cozinha', 'panela', 'frigideira', 'liquidificador', 'air fryer'], '🍳 Uma opção prática para a cozinha e para o dia a dia.'),
        (['ferramenta', 'furadeira', 'parafusadeira', 'serra'], '🔧 Uma opção interessante para quem gosta de ferramentas e trabalhos em casa.'),
        (['livro', 'romance', 'literatura'], '📚 Uma opção para quem gosta de leitura ou procura um presente.'),
        (['cama', 'mesa', 'cadeira', 'sofá', 'decoração', 'almofada'], '🏠 Uma opção para deixar a casa mais confortável e bonita.'),
    ]

    for words, text in groups:
        if any(word in t for word in words):
            return text

    return '✨ Uma oferta que vale a pena conferir enquanto o preço está disponível.'


def build_caption(o):
    title = html.escape(str(o.title or 'Oferta')[:180])
    kind = product_kind(o.title)

    # Escolhe uma chamada diferente para não deixar todas as publicações iguais.
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
