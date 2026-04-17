import os
import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_IDS = os.getenv("TELEGRAM_CHAT_IDS")


def send_telegram_message(text: str) -> bool:
    if not TOKEN or not CHAT_IDS:
        return False

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    chat_ids = [chat_id.strip() for chat_id in CHAT_IDS.split(",") if chat_id.strip()]

    success = False

    for chat_id in chat_ids:
        try:
            response = requests.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": text,
                },
                timeout=10,
            )
            if response.ok:
                success = True
        except Exception:
            pass

    return success
