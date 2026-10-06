import json
from dataclasses import dataclass
from urllib.parse import urljoin
import httpx
from app.config import settings
from app.crypto import decrypt


@dataclass
class Offer:
    external_id: str
    merchant: str
    title: str
    url: str
    image_url: str = ''
    price: float | None = None
    old_price: float | None = None
    commission: float | None = None
    score: float = 0
    raw_json: str = '{}'


def _num(v):
    if v is None or v == '':
        return None
    try:
        return float(str(v).replace('%','').replace('R$','').replace(' ','').replace('.','').replace(',','.'))
    except Exception:
        try: return float(v)
        except Exception: return None


def _first(x, *keys, default=''):
    for k in keys:
        v = x.get(k)
        if v not in (None, ''):
            return v
    return default


class LomadeeAdapter:
    """Cliente da API REST da Lomadee.

    A documentação mostrada pelo usuário define x-api-key e endpoints como
    /affiliate/products, /affiliate/brands, /affiliate/campaigns e /affiliate/shortener/urls.
    O endpoint de criação de short link permanece configurável porque a documentação
    exibida mostra a permissão de leitura do shortener; não inventamos um POST.
    """
    def __init__(self, client_row=None):
        self.client = client_row
        self.api_key = decrypt(client_row['api_key_enc']) if client_row and client_row['api_key_enc'] else ''
        self.source_id = (client_row['source_id'] if client_row else '') or ''
        self.campaign = (client_row['campaign'] if client_row else '') or ''

    def _url(self, path):
        return urljoin(settings.lomadee_base_url + '/', path.lstrip('/'))

    def _headers(self):
        if not self.api_key:
            raise RuntimeError('API Key da Lomadee não cadastrada.')
        return {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': 'LomadeeAutoBot/2.0',
            'x-api-key': self.api_key,
        }

    async def _get(self, path, params=None):
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
            r = await c.get(self._url(path), params=params or {}, headers=self._headers())
        if r.status_code in (401,403):
            raise RuntimeError('API Key recusada ou sem o escopo necessário pela Lomadee.')
        if r.status_code >= 400:
            raise RuntimeError(f'Lomadee HTTP {r.status_code}: {r.text[:300]}')
        try: return r.json()
        except Exception: raise RuntimeError('A Lomadee respondeu algo que não é JSON.')

    async def test_connection(self):
        # brands:read is one of the documented affiliate scopes.
        return await self._get(settings.lomadee_brands_path)

    async def products(self, limit=30):
        params = {'limit': limit}
        if self.source_id: params['sourceId'] = self.source_id
        if self.campaign: params['campaign'] = self.campaign
        data = await self._get(settings.lomadee_products_path, params)
        if isinstance(data, list): items = data
        elif isinstance(data, dict):
            items = data.get('products') or data.get('data') or data.get('items') or data.get('results') or []
        else: items = []
        result=[]
        for x in items:
            if not isinstance(x, dict): continue
            destination = str(_first(x,'affiliateUrl','trackingUrl','deeplink','deepLink','shortUrl','url','productUrl',default=''))
            result.append(Offer(
                external_id=str(_first(x,'id','productId','offerId',default=destination)),
                merchant=str(_first(x,'merchant','store','brand','brandName',default='Lomadee')),
                title=str(_first(x,'title','name','productName',default='Oferta')),
                url=destination,
                image_url=str(_first(x,'image','imageUrl','thumbnail','thumbnailUrl','picture',default='')),
                price=_num(_first(x,'price','salePrice','currentPrice',default=None)),
                old_price=_num(_first(x,'oldPrice','originalPrice','listPrice',default=None)),
                commission=_num(_first(x,'commission','commissionRate','commissionPercentage',default=None)),
                raw_json=json.dumps(x,ensure_ascii=False),
            ))
        return result

    async def affiliate_url(self, destination_url: str) -> str:
        # Some product payloads already contain the affiliate/tracking URL.
        if destination_url and destination_url.startswith(('http://','https://')):
            return destination_url
        if not settings.lomadee_shortener_create_url:
            raise RuntimeError('A API retornou produto sem link. Configure LOMADEE_SHORTENER_CREATE_URL quando a documentação da Lomadee indicar o endpoint de criação do link.')
        payload = {'url': destination_url}
        if self.source_id: payload['sourceId'] = self.source_id
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
            r = await c.post(settings.lomadee_shortener_create_url, json=payload, headers=self._headers())
        if r.status_code >= 400:
            raise RuntimeError(f'Erro ao criar link Lomadee: HTTP {r.status_code}: {r.text[:300]}')
        data = r.json()
        if isinstance(data, dict):
            return str(_first(data,'shortUrl','url','deeplink','deepLink','trackingUrl',default=''))
        return ''
