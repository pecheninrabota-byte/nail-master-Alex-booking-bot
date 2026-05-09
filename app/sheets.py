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
    "confirmed": "Подтверждена",
    "cancelled": "Отменена",
    "rescheduled": "Перенесена",
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


def _booking_status_ru(value: str):
    return BOOKING_STATUS_RU.get(value, value or "")


def _client_status_ru(value: str):
    return CLIENT_STATUS_RU.get(value, value or "")


def _normalize_row(row: list):
    """
    Колонки:
    A Booking ID
    B Дата
    C Время
    D Имя
    E Контакт
    F Услуга
    G Стоимость
    H Комментарий
    I Статус записи
    J Статус клиента
    K Способ связи
    """

    result = list(row)

    while len(result) < 11:
        result.append("")

    # Дата и время строго текстом, чтобы Google Sheets не превращал время в 0,4791666667
    result[1] = str(result[1] or "")
    result[2] = str(result[2] or "")

    # Статусы на русском
    result[8] = _booking_status_ru(str(result[8] or ""))
    result[9] = _client_status_ru(str(result[9] or ""))

    return result


def append_booking_row(row: list):
    service = _get_service()
    normalized_row = _normalize_row(row)

result = service.spreadsheets().values().append(
    spreadsheetId=SPREADSHEET_ID,
    range=f"{SHEET_NAME}!A2:K",
    valueInputOption="RAW",
    insertDataOption="OVERWRITE",
    body={"values": [normalized_row]},
).execute()

    logger.info("Google Sheets row appended: %s", result)
    return result


def update_booking_status(booking_id: str, new_status: str):
    service = _get_service()

    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A2:Z",
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
        range=f"{SHEET_NAME}!A2:Z",
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
