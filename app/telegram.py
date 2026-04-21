import logging
import os
from typing import List, Dict, Any, Optional

import requests

logger = logging.getLogger("uvicorn.error")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_IDS_RAW = os.getenv("TELEGRAM_CHAT_IDS")


def get_chat_ids() -> List[str]:
    if not CHAT_IDS_RAW:
        return []
    return [chat_id.strip() for chat_id in CHAT_IDS_RAW.split(",") if chat_id.strip()]


def send_telegram_message(text: str) -> Dict[str, Any]:
    if not TOKEN:
        logger.error("Telegram disabled: TELEGRAM_BOT_TOKEN is missing")
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN is missing", "details": []}

    chat_ids = get_chat_ids()
    if not chat_ids:
        logger.error("Telegram disabled: TELEGRAM_CHAT_IDS is missing or empty")
        return {"ok": False, "error": "TELEGRAM_CHAT_IDS is missing or empty", "details": []}

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    details = []
    success = False

    for chat_id in chat_ids:
        try:
            response = requests.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                },
                timeout=15,
            )

            detail = {
                "chat_id": chat_id,
                "status_code": response.status_code,
                "ok": response.ok,
                "response_text": response.text,
            }
            details.append(detail)

            if response.ok:
                success = True
                logger.info("Telegram sent successfully to chat_id=%s", chat_id)
            else:
                logger.error(
                    "Telegram API error for chat_id=%s: status=%s body=%s",
                    chat_id,
                    response.status_code,
                    response.text,
                )

        except Exception as e:
            details.append({
                "chat_id": chat_id,
                "status_code": None,
                "ok": False,
                "response_text": str(e),
            })
            logger.exception("Telegram send crashed for chat_id=%s", chat_id)

    return {
        "ok": success,
        "error": None if success else "Failed to send message to all chat_ids",
        "details": details,
    }


def format_booking_created_message(
    client_name: str,
    contact: str,
    service_name: str,
    date: str,
    time: str,
    price: Optional[int] = None,
    preferred_contact_method: Optional[str] = None,
    comment: Optional[str] = None,
) -> str:
    parts = [
        "💅 <b>Новая запись</b>",
        f"<b>Клиент:</b> {client_name}",
        f"<b>Контакт:</b> {contact}",
        f"<b>Действие:</b> записался на услугу",
        f"<b>Услуга:</b> {service_name}",
        f"<b>Дата:</b> {date}",
        f"<b>Время:</b> {time}",
    ]

    if price is not None:
        parts.append(f"<b>Стоимость:</b> {price} ₽")

    if preferred_contact_method:
        parts.append(f"<b>Способ связи:</b> {preferred_contact_method}")

    if comment:
        parts.append(f"<b>Комментарий:</b> {comment}")

    return "\n".join(parts)


def format_booking_cancelled_message(
    client_name: str,
    contact: str,
    service_name: str,
    date: str,
    time: str,
    preferred_contact_method: Optional[str] = None,
    cancel_reason: Optional[str] = None,
) -> str:
    parts = [
        "❌ <b>Отмена записи</b>",
        f"<b>Клиент:</b> {client_name}",
        f"<b>Контакт:</b> {contact}",
        f"<b>Действие:</b> отменил запись",
        f"<b>Услуга:</b> {service_name}",
        f"<b>Дата:</b> {date}",
        f"<b>Время:</b> {time}",
    ]

    if preferred_contact_method:
        parts.append(f"<b>Способ связи:</b> {preferred_contact_method}")

    if cancel_reason:
        parts.append(f"<b>Причина:</b> {cancel_reason}")

    return "\n".join(parts)


def format_booking_rescheduled_message(
    client_name: str,
    contact: str,
    service_name: str,
    old_date: str,
    old_time: str,
    new_date: str,
    new_time: str,
    preferred_contact_method: Optional[str] = None,
    comment: Optional[str] = None,
) -> str:
    parts = [
        "🔁 <b>Перенос записи</b>",
        f"<b>Клиент:</b> {client_name}",
        f"<b>Контакт:</b> {contact}",
        f"<b>Действие:</b> перенёс запись",
        f"<b>Услуга:</b> {service_name}",
        f"<b>Было:</b> {old_date} {old_time}",
        f"<b>Стало:</b> {new_date} {new_time}",
    ]

    if preferred_contact_method:
        parts.append(f"<b>Способ связи:</b> {preferred_contact_method}")

    if comment:
        parts.append(f"<b>Комментарий:</b> {comment}")

    return "\n".join(parts)


def format_contact_request_message(
    client_name: str,
    contact: str,
    preferred_contact_method: Optional[str] = None,
    comment: Optional[str] = None,
) -> str:
    parts = [
        "📩 <b>Новая заявка на связь</b>",
        f"<b>Клиент:</b> {client_name}",
        f"<b>Контакт:</b> {contact}",
        f"<b>Действие:</b> хочет связаться с мастером",
    ]

    if preferred_contact_method:
        parts.append(f"<b>Способ связи:</b> {preferred_contact_method}")

    if comment:
        parts.append(f"<b>Комментарий:</b> {comment}")

    return "\n".join(parts)
