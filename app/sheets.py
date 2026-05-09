import json
import logging
import os

from google.oauth2 import service_account
from googleapiclient.discovery import build

logger = logging.getLogger("uvicorn.error")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

SPREADSHEET_ID = os.getenv("GOOGLE_SHEET_ID")
SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "Лист1")


BOOKING_STATUS_RU = {
    "confirmed": "Ожидает подтверждения",
    "waiting_confirmation": "Ожидает подтверждения",
    "cancelled": "Отменена",
    "rescheduled": "Перенесена",
    "completed": "Завершена",
    "no_show": "Не пришёл",
    "debug": "Тест",
}

CLIENT_STATUS_RU = {
    "new": "Новый клиент",
    "returned": "Повторный клиент",
    "regular": "Постоянный клиент",
    "left": "Ушёл",
    "claim": "Рекламация",
    "blacklist": "Чёрный список",
}


CLOSED_BOOKING_STATUSES_RU = {
    "Отменена",
    "Завершена",
    "Не пришёл",
}


def _get_service():
    raw_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")

    if not raw_json:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON is missing")

    if not SPREADSHEET_ID:
        raise RuntimeError("GOOGLE_SHEET_ID is missing")

    creds = service_account.Credentials.from_service_account_info(
        json.loads(raw_json),
        scopes=SCOPES,
    )

    return build("sheets", "v4", credentials=creds)


def _normalize_contact(contact: str):
    if not contact:
        return ""

    normalized = str(contact).strip().lower()

    normalized = normalized.replace(" ", "")
    normalized = normalized.replace("-", "")
    normalized = normalized.replace("(", "")
    normalized = normalized.replace(")", "")

    if normalized.startswith("+7"):
        normalized = "7" + normalized[2:]

    if normalized.startswith("8") and len(normalized) >= 11:
        normalized = "7" + normalized[1:]

    if normalized.startswith("@"):
        normalized = normalized[1:]

    return normalized


def _booking_status_ru(value: str):
    return BOOKING_STATUS_RU.get(value, value or "")


def _client_status_ru(value: str):
    return CLIENT_STATUS_RU.get(value, value or "")


def _normalize_row(row: list):
    result = list(row)

    while len(result) < 11:
        result.append("")

    result = result[:11]

    result[1] = str(result[1] or "")
    result[2] = str(result[2] or "")
    result[8] = _booking_status_ru(str(result[8] or ""))
    result[9] = _client_status_ru(str(result[9] or ""))

    return result


def _find_next_empty_row(service):
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A2:A",
    ).execute()

    rows = result.get("values", [])

    return len(rows) + 2


def append_booking_row(row: list):
    service = _get_service()
    normalized_row = _normalize_row(row)
    next_row = _find_next_empty_row(service)

    result = service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A{next_row}:K{next_row}",
        valueInputOption="RAW",
        body={"values": [normalized_row]},
    ).execute()

    logger.info("Google Sheets row written to row %s: %s", next_row, result)
    return result


def update_booking_status(booking_id: str, new_status: str):
    service = _get_service()

    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A2:K",
    ).execute()

    rows = result.get("values", [])

    for i, row in enumerate(rows):
        if row and row[0] == booking_id:
            row_index = i + 2

            service.spreadsheets().values().update(
                spreadsheetId=SPREADSHEET_ID,
                range=f"{SHEET_NAME}!I{row_index}",
                valueInputOption="RAW",
                body={"values": [[_booking_status_ru(new_status)]]},
            ).execute()

            logger.info("Google Sheets booking status updated: %s -> %s", booking_id, new_status)
            return True

    logger.warning("Google Sheets booking_id not found: %s", booking_id)
    return False


def update_booking_row_after_reschedule(
    booking_id: str,
    new_date: str,
    new_time: str,
    new_status: str = "rescheduled",
):
    service = _get_service()

    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A2:K",
    ).execute()

    rows = result.get("values", [])

    for i, row in enumerate(rows):
        if row and row[0] == booking_id:
            row_index = i + 2

            service.spreadsheets().values().batchUpdate(
                spreadsheetId=SPREADSHEET_ID,
                body={
                    "valueInputOption": "RAW",
                    "data": [
                        {
                            "range": f"{SHEET_NAME}!B{row_index}:C{row_index}",
                            "values": [[str(new_date), str(new_time)]],
                        },
                        {
                            "range": f"{SHEET_NAME}!I{row_index}",
                            "values": [[_booking_status_ru(new_status)]],
                        },
                    ],
                },
            ).execute()

            logger.info("Google Sheets booking rescheduled: %s", booking_id)
            return True

    logger.warning("Google Sheets booking_id not found for reschedule: %s", booking_id)
    return False


def get_manual_client_status_by_contact(contact: str):
    service = _get_service()
    normalized_contact = _normalize_contact(contact)

    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A2:K",
    ).execute()

    rows = result.get("values", [])

    # Идём снизу вверх, чтобы брать самый свежий статус клиента
    for row in reversed(rows):
        if len(row) >= 10:
            row_contact = _normalize_contact(row[4])
            client_status = row[9]

            if row_contact == normalized_contact:
                return client_status

    return None


def is_contact_blacklisted_in_sheet(contact: str):
    service = _get_service()
    normalized_contact = _normalize_contact(contact)

    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A2:K",
    ).execute()

    rows = result.get("values", [])

    for row in rows:
        if len(row) >= 10:
            row_contact = _normalize_contact(row[4])
            client_status = str(row[9] or "").strip()

            if row_contact == normalized_contact and client_status == "Чёрный список":
                return True

    return False


def get_manual_booking_status_by_id(booking_id: str):
    service = _get_service()

    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A2:K",
    ).execute()

    rows = result.get("values", [])

    for row in rows:
        if row and row[0] == booking_id:
            if len(row) >= 9:
                return row[8]
            return None

    return None


def is_booking_active_by_sheet(booking_id: str):
    status = get_manual_booking_status_by_id(booking_id)

    # Если строки в Sheets нет, не блокируем — ориентируемся на Postgres
    if not status:
        return True

    return status not in CLOSED_BOOKING_STATUSES_RU
