import uuid
from datetime import datetime, timedelta, timezone

import httpx
from dotenv import dotenv_values

ENV = dotenv_values("/home/ubuntu/LOMADEE-AUTOBOT/.env")

TOKEN = (ENV.get("MERCADOPAGO_ACCESS_TOKEN") or "").strip()
PRICE = float(ENV.get("SUBSCRIPTION_PRICE") or "15.00")
DAYS = int(ENV.get("SUBSCRIPTION_DAYS") or "30")

API = "https://api.mercadopago.com"


def _headers():
    if not TOKEN:
        raise RuntimeError("MERCADOPAGO_ACCESS_TOKEN não configurado.")

    return {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "X-Idempotency-Key": str(uuid.uuid4()),
    }


async def create_pix(telegram_id, name="Cliente"):
    email = f"telegram{telegram_id}@clientes.bot"

    payload = {
        "transaction_amount": PRICE,
        "description": "Assinatura mensal - Lomadee Auto Offers",
        "payment_method_id": "pix",
        "payer": {
            "email": email,
            "first_name": (name or "Cliente")[:50],
        },
        "external_reference": (
            f"subscription:{telegram_id}:{uuid.uuid4().hex}"
        ),
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{API}/v1/payments",
            json=payload,
            headers=_headers(),
        )

    if response.status_code >= 400:
        raise RuntimeError(
            f"Mercado Pago HTTP {response.status_code}: "
            f"{response.text[:500]}"
        )

    data = response.json()

    transaction = (
        data.get("point_of_interaction", {})
        .get("transaction_data", {})
    )

    return {
        "payment_id": str(data.get("id", "")),
        "status": data.get("status", ""),
        "qr_code": transaction.get("qr_code", ""),
        "qr_code_base64": transaction.get("qr_code_base64", ""),
        "ticket_url": transaction.get("ticket_url", ""),
        "external_reference": data.get("external_reference", ""),
    }


async def get_payment(payment_id):
    if not TOKEN:
        raise RuntimeError("MERCADOPAGO_ACCESS_TOKEN não configurado.")

    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            f"{API}/v1/payments/{payment_id}",
            headers=headers,
        )

    if response.status_code >= 400:
        raise RuntimeError(
            f"Mercado Pago HTTP {response.status_code}: "
            f"{response.text[:500]}"
        )

    return response.json()


def approved(payment):
    return payment.get("status") == "approved"


def expiration_from_now():
    return datetime.now(timezone.utc) + timedelta(days=DAYS)
