def score_offer(o):
    score = 0.0
    if o.old_price and o.price and o.old_price > o.price:
        discount = (o.old_price-o.price)/o.old_price*100
        score += min(50, discount*1.7)
    if o.commission is not None:
        score += min(20, o.commission*2.5)
    if o.image_url: score += 10
    if o.url: score += 10
    if o.title and len(o.title) > 8: score += 10
    return round(min(100, score), 2)
