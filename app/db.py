import sqlite3
from pathlib import Path
from app.config import settings

Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)


def conn():
    c = sqlite3.connect(settings.db_path)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c


def _columns(db, table):
    return {r['name'] for r in db.execute(f'PRAGMA table_info({table})')}


def init_db():
    with conn() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS clients (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          telegram_id INTEGER UNIQUE NOT NULL,
          name TEXT NOT NULL,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          active INTEGER DEFAULT 0,
          chat_id INTEGER,
          post_interval INTEGER DEFAULT 30,
          daily_limit INTEGER DEFAULT 12
        );
        CREATE TABLE IF NOT EXISTS affiliate_accounts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          client_id INTEGER UNIQUE NOT NULL,
          email TEXT,
          affiliate_id TEXT,
          source_id TEXT,
          api_key_enc TEXT,
          campaign TEXT DEFAULT 'shopee',
          status TEXT DEFAULT 'configured',
          last_error TEXT,
          checked_at TEXT,
          FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS offers (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          external_id TEXT NOT NULL,
          merchant TEXT,
          title TEXT NOT NULL,
          url TEXT NOT NULL,
          image_url TEXT,
          price REAL,
          old_price REAL,
          commission REAL,
          score REAL DEFAULT 0,
          raw_json TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(external_id)
        );
        CREATE TABLE IF NOT EXISTS posts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          client_id INTEGER NOT NULL,
          offer_id INTEGER NOT NULL,
          affiliate_url TEXT NOT NULL,
          telegram_message_id INTEGER,
          posted_at TEXT DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(client_id, offer_id),
          FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE CASCADE,
          FOREIGN KEY(offer_id) REFERENCES offers(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_posts_client_date ON posts(client_id, posted_at);
        ''')
        # Small migration for installations made from the first prototype.
        cols = _columns(db, 'affiliate_accounts')
        if 'api_key_enc' not in cols:
            db.execute('ALTER TABLE affiliate_accounts ADD COLUMN api_key_enc TEXT')
        if 'last_error' not in cols:
            db.execute('ALTER TABLE affiliate_accounts ADD COLUMN last_error TEXT')
        if 'checked_at' not in cols:
            db.execute('ALTER TABLE affiliate_accounts ADD COLUMN checked_at TEXT')


def get_client(telegram_id):
    with conn() as db:
        return db.execute('SELECT * FROM clients WHERE telegram_id=?', (telegram_id,)).fetchone()


def upsert_client(telegram_id, name):
    with conn() as db:
        db.execute('''INSERT INTO clients(telegram_id,name) VALUES(?,?)
                      ON CONFLICT(telegram_id) DO UPDATE SET name=excluded.name''', (telegram_id, name))
    return get_client(telegram_id)


def save_affiliate(client_id, data):
    with conn() as db:
        db.execute('''INSERT INTO affiliate_accounts
            (client_id,email,affiliate_id,source_id,api_key_enc,campaign,status,last_error)
            VALUES(?,?,?,?,?,?,?,NULL)
            ON CONFLICT(client_id) DO UPDATE SET
              email=excluded.email, affiliate_id=excluded.affiliate_id,
              source_id=excluded.source_id, api_key_enc=excluded.api_key_enc,
              campaign=excluded.campaign, status=excluded.status,
              last_error=NULL''',
            (client_id, data.get('email',''), data.get('affiliate_id',''), data.get('source_id',''),
             data.get('api_key_enc',''), data.get('campaign','shopee'), data.get('status','configured')))


def get_affiliate(client_id):
    with conn() as db:
        return db.execute('SELECT * FROM affiliate_accounts WHERE client_id=?', (client_id,)).fetchone()


def set_affiliate_status(client_id, status, error=None):
    with conn() as db:
        db.execute('''UPDATE affiliate_accounts SET status=?, last_error=?, checked_at=CURRENT_TIMESTAMP WHERE client_id=?''', (status, error, client_id))


def set_chat(client_id, chat_id):
    with conn() as db:
        db.execute('UPDATE clients SET chat_id=? WHERE id=?', (chat_id, client_id))


def set_active(client_id, active):
    with conn() as db:
        db.execute('UPDATE clients SET active=? WHERE id=?', (1 if active else 0, client_id))


def clients_active():
    with conn() as db:
        return db.execute('''SELECT c.*, a.email, a.affiliate_id, a.source_id, a.api_key_enc,
                                    a.campaign, a.status AS lomadee_status, a.last_error
                             FROM clients c JOIN affiliate_accounts a ON a.client_id=c.id
                             WHERE c.active=1''').fetchall()


def save_offer(o):
    with conn() as db:
        db.execute('''INSERT INTO offers(external_id,merchant,title,url,image_url,price,old_price,commission,score,raw_json)
                      VALUES(?,?,?,?,?,?,?,?,?,?)
                      ON CONFLICT(external_id) DO UPDATE SET
                        title=excluded.title,url=excluded.url,image_url=excluded.image_url,
                        price=excluded.price,old_price=excluded.old_price,
                        commission=excluded.commission,score=excluded.score,raw_json=excluded.raw_json''',
                   (o.external_id,o.merchant,o.title,o.url,o.image_url,o.price,o.old_price,o.commission,o.score,o.raw_json))
        return db.execute('SELECT * FROM offers WHERE external_id=?', (o.external_id,)).fetchone()


def was_posted(client_id, offer_id, offer_url=None):
    with conn() as db:
        if db.execute(
            'SELECT 1 FROM posts WHERE client_id=? AND offer_id=?',
            (client_id, offer_id)
        ).fetchone():
            return True

        if offer_url:
            url = str(offer_url).strip().rstrip('/').lower()
            if url:
                return bool(db.execute(
                    "SELECT 1 FROM posts p JOIN offers o ON o.id=p.offer_id "
                    "WHERE p.client_id=? AND lower(rtrim(o.url, '/'))=?",
                    (client_id, url)
                ).fetchone())

        return False

def count_posts_today(client_id):
    with conn() as db:
        return db.execute("SELECT COUNT(*) FROM posts WHERE client_id=? AND date(posted_at,'localtime')=date('now','localtime')", (client_id,)).fetchone()[0]


def save_post(client_id, offer_id, affiliate_url, message_id):
    with conn() as db:
        db.execute('INSERT OR IGNORE INTO posts(client_id,offer_id,affiliate_url,telegram_message_id) VALUES(?,?,?,?)', (client_id,offer_id,affiliate_url,message_id))


def list_clients():
    with conn() as db:
        return db.execute('''SELECT c.*, a.email, a.affiliate_id, a.campaign, a.status AS lomadee_status
                             FROM clients c LEFT JOIN affiliate_accounts a ON a.client_id=c.id ORDER BY c.id DESC''').fetchall()


def health():
    with conn() as db:
        return db.execute('SELECT (SELECT COUNT(*) FROM clients),(SELECT COUNT(*) FROM offers),(SELECT COUNT(*) FROM posts)').fetchone()


if __name__ == '__main__':
    init_db()
    print('Banco inicializado:', settings.db_path)

# ===== ASSINATURAS / MERCADO PAGO =====

def _ensure_subscription_tables():
    with conn() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS subscriptions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          client_id INTEGER UNIQUE NOT NULL,
          status TEXT DEFAULT 'inactive',
          expires_at TEXT,
          payment_id TEXT,
          updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS payments (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          client_id INTEGER NOT NULL,
          payment_id TEXT UNIQUE NOT NULL,
          amount REAL NOT NULL,
          status TEXT DEFAULT 'pending',
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE CASCADE
        );
        ''')


def subscription(client_id):
    _ensure_subscription_tables()
    with conn() as db:
        return db.execute(
            'SELECT * FROM subscriptions WHERE client_id=?',
            (client_id,)
        ).fetchone()


def save_payment(client_id, payment_id, amount):
    _ensure_subscription_tables()
    with conn() as db:
        db.execute('''
            INSERT OR REPLACE INTO payments
            (client_id, payment_id, amount, status)
            VALUES (?, ?, ?, 'pending')
        ''', (client_id, str(payment_id), float(amount)))


def payment_status(payment_id, status):
    _ensure_subscription_tables()
    with conn() as db:
        db.execute(
            'UPDATE payments SET status=? WHERE payment_id=?',
            (status, str(payment_id))
        )


def activate_subscription(client_id, payment_id, days=30):
    _ensure_subscription_tables()

    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)

    with conn() as db:
        old = db.execute(
            'SELECT expires_at FROM subscriptions WHERE client_id=?',
            (client_id,)
        ).fetchone()

        base = now

        if old and old['expires_at']:
            try:
                old_exp = datetime.fromisoformat(
                    old['expires_at'].replace('Z', '+00:00')
                )
                if old_exp > now:
                    base = old_exp
            except Exception:
                pass

        expires = base + timedelta(days=days)

        db.execute('''
            INSERT INTO subscriptions
            (client_id, status, expires_at, payment_id, updated_at)
            VALUES (?, 'active', ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(client_id) DO UPDATE SET
              status='active',
              expires_at=excluded.expires_at,
              payment_id=excluded.payment_id,
              updated_at=CURRENT_TIMESTAMP
        ''', (client_id, expires.isoformat(), str(payment_id)))

        db.execute(
            'UPDATE payments SET status="approved" WHERE payment_id=?',
            (str(payment_id),)
        )

        return expires.isoformat()


def has_active_subscription(client_id):
    _ensure_subscription_tables()

    with conn() as db:
        row = db.execute('''
            SELECT status, expires_at
            FROM subscriptions
            WHERE client_id=?
        ''', (client_id,)).fetchone()

    if not row or row['status'] != 'active' or not row['expires_at']:
        return False

    from datetime import datetime, timezone

    try:
        expires = datetime.fromisoformat(
            row['expires_at'].replace('Z', '+00:00')
        )
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)

        if expires > datetime.now(timezone.utc):
            return True
    except Exception:
        pass

    with conn() as db:
        db.execute(
            'UPDATE subscriptions SET status="expired" WHERE client_id=?',
            (client_id,)
        )

    return False

def pending_payments():
    _ensure_subscription_tables()
    with conn() as db:
        return db.execute('''
            SELECT p.*, c.telegram_id, c.name
            FROM payments p
            JOIN clients c ON c.id = p.client_id
            WHERE p.status = 'pending'
            ORDER BY p.id ASC
        ''').fetchall()

# ===== CONFIGURAÇÕES POR CLIENTE =====

def _ensure_client_config_table():
    with conn() as db:
        db.execute('''
            CREATE TABLE IF NOT EXISTS client_config (
                client_id INTEGER PRIMARY KEY,
                interval_minutes INTEGER DEFAULT 30,
                stores_json TEXT DEFAULT '[]',
                popular_enabled INTEGER DEFAULT 1,
                FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE CASCADE
            )
        ''')


def get_client_config(client_id):
    _ensure_client_config_table()
    import json

    with conn() as db:
        row = db.execute(
            'SELECT * FROM client_config WHERE client_id=?',
            (client_id,)
        ).fetchone()

        if not row:
            db.execute('''
                INSERT INTO client_config
                (client_id, interval_minutes, stores_json, popular_enabled)
                VALUES (?, 30, '[]', 1)
            ''', (client_id,))

            row = db.execute(
                'SELECT * FROM client_config WHERE client_id=?',
                (client_id,)
            ).fetchone()

    try:
        stores = json.loads(row['stores_json'] or '[]')
        if not isinstance(stores, list):
            stores = []
    except Exception:
        stores = []

    return {
        'client_id': row['client_id'],
        'interval_minutes': int(row['interval_minutes'] or 30),
        'stores': stores,
        'popular_enabled': bool(row['popular_enabled']),
    }


def save_client_config(
    client_id,
    interval_minutes=None,
    stores=None,
    popular_enabled=None
):
    _ensure_client_config_table()
    import json

    current = get_client_config(client_id)

    if interval_minutes is None:
        interval_minutes = current['interval_minutes']

    if stores is None:
        stores = current['stores']

    if popular_enabled is None:
        popular_enabled = current['popular_enabled']

    with conn() as db:
        db.execute('''
            INSERT INTO client_config
            (client_id, interval_minutes, stores_json, popular_enabled)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(client_id) DO UPDATE SET
                interval_minutes=excluded.interval_minutes,
                stores_json=excluded.stores_json,
                popular_enabled=excluded.popular_enabled
        ''', (
            client_id,
            int(interval_minutes),
            json.dumps(stores, ensure_ascii=False),
            1 if popular_enabled else 0
        ))


def last_post_at(client_id):
    with conn() as db:
        row = db.execute('''
            SELECT posted_at
            FROM posts
            WHERE client_id=?
            ORDER BY posted_at DESC
            LIMIT 1
        ''', (client_id,)).fetchone()

    return row['posted_at'] if row else None


def set_daily_limit(client_id, daily_limit):
    with conn() as db:
        db.execute(
            "UPDATE clients SET daily_limit=? WHERE id=?",
            (int(daily_limit), client_id)
        )

def get_daily_limit(client_id):
    with conn() as db:
        row = db.execute(
            "SELECT daily_limit FROM clients WHERE id=?",
            (client_id,)
        ).fetchone()
    return int(row["daily_limit"] or 12) if row else 12
