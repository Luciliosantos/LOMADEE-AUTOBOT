import html

def money(v):
    return f'R$ {v:,.2f}'.replace(',','X').replace('.',',').replace('X','.')

def build_caption(o):
    title = html.escape(o.title[:180])
    lines = ['🔥 <b>OFERTA DO DIA!</b>', '', f'🛍️ <b>{title}</b>']
    if o.old_price and o.price and o.old_price > o.price:
        disc = (1-o.price/o.old_price)*100
        lines += [f'💰 De <s>{money(o.old_price)}</s> por <b>{money(o.price)}</b>', f'🏷️ <b>{disc:.0f}% OFF</b>']
    elif o.price:
        lines += [f'💰 <b>{money(o.price)}</b>']
    if o.commission is not None:
        lines += [f'💸 Comissão: até <b>{o.commission:g}%</b>']
    lines += ['', '⚡ Pode acabar ou mudar de preço a qualquer momento.', '👇 <b>CLIQUE EM VER OFERTA</b>']
    return '\n'.join(lines)
