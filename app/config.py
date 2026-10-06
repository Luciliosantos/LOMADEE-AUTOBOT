import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _ints(value: str):
    return tuple(int(x.strip()) for x in value.split(',') if x.strip().isdigit())


@dataclass(frozen=True)
class Settings:
    bot_token: str = os.getenv('BOT_TOKEN', '')
    admin_ids: tuple[int, ...] = _ints(os.getenv('ADMIN_IDS', ''))
    lomadee_base_url: str = os.getenv('LOMADEE_BASE_URL', 'https://api.lomadee.com.br').rstrip('/')
    lomadee_products_path: str = os.getenv('LOMADEE_PRODUCTS_PATH', '/affiliate/products')
    lomadee_brands_path: str = os.getenv('LOMADEE_BRANDS_PATH', '/affiliate/brands')
    lomadee_campaigns_path: str = os.getenv('LOMADEE_CAMPAIGNS_PATH', '/affiliate/campaigns')
    lomadee_shortener_path: str = os.getenv('LOMADEE_SHORTENER_PATH', '/affiliate/shortener/urls')
    lomadee_shortener_create_url: str = os.getenv('LOMADEE_SHORTENER_CREATE_URL', '')
    interval_minutes: int = int(os.getenv('POST_INTERVAL_MINUTES', '30'))
    max_posts_day: int = int(os.getenv('MAX_POSTS_PER_DAY', '12'))
    min_score: int = int(os.getenv('MIN_SCORE', '55'))
    timezone: str = os.getenv('TIMEZONE', 'America/Sao_Paulo')
    db_path: str = os.getenv('DB_PATH', './data/bot.db')
    master_key: str = os.getenv('MASTER_KEY', '')
    owner_referral_url: str = os.getenv('OWNER_REFERRAL_URL', '')
    openai_api_key: str = os.getenv('OPENAI_API_KEY', '')
    openai_model: str = os.getenv('OPENAI_MODEL', 'gpt-5-mini')


settings = Settings()
