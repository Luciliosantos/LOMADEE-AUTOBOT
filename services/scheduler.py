from datetime import datetime, timezone

from telegram.ext import Application

from app import db
from app.config import settings
from services.publisher import publish_one
from services.payments import get_payment, approved, DAYS


def _seconds_since(value):
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(
            str(value).replace('Z', '+00:00')
        )

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return (
            datetime.now(timezone.utc) - dt
        ).total_seconds()

    except Exception:
        return None


async def scheduled_job(context):

    for client in db.clients_active():

        try:
            # Assinatura protege a automação também.
            is_admin = (
                client["telegram_id"]
                in settings.admin_ids
            )

            if not is_admin:
                if not db.has_active_subscription(
                    client["id"]
                ):
                    continue

            config = db.get_client_config(
                client["id"]
            )

            interval = max(
                5,
                int(config["interval_minutes"])
            )

            last = db.last_post_at(
                client["id"]
            )

            elapsed = _seconds_since(last)

            if elapsed is not None:
                if elapsed < interval * 60:
                    continue

            await publish_one(
                context.bot,
                client,
                settings.min_score
            )

            print(
                f'[scheduler] cliente={client["id"]} '
                f'intervalo={interval}min oferta publicada'
            )

        except Exception as e:

            print(
                f'[scheduler] cliente={client["id"]}: {e}'
            )


async def payment_job(context):

    for payment in db.pending_payments():

        try:

            data = await get_payment(
                payment["payment_id"]
            )

            status = data.get(
                "status",
                "pending"
            )

            if approved(data):

                db.activate_subscription(
                    payment["client_id"],
                    payment["payment_id"],
                    DAYS
                )

                await context.bot.send_message(
                    chat_id=payment["telegram_id"],
                    text=(
                        "✅ PAGAMENTO CONFIRMADO!\n\n"
                        "🔓 Sua assinatura foi ativada.\n"
                        "📅 Validade: 30 dias.\n\n"
                        "🚀 Agora você já pode usar o bot."
                    )
                )

                print(
                    f'[payment] aprovado '
                    f'payment={payment["payment_id"]} '
                    f'cliente={payment["client_id"]}'
                )

            else:

                print(
                    f'[payment] payment={payment["payment_id"]} '
                    f'status={status}'
                )

        except Exception as e:

            print(
                f'[payment] erro payment='
                f'{payment["payment_id"]}: {e}'
            )


def install_scheduler(app: Application):

    # Verifica os clientes a cada minuto.
    # O intervalo individual de cada cliente
    # é respeitado dentro de scheduled_job().
    app.job_queue.run_repeating(
        scheduled_job,
        interval=60,
        first=20
    )

    # Mercado Pago continua automático.
    app.job_queue.run_repeating(
        payment_job,
        interval=30,
        first=10
    )
