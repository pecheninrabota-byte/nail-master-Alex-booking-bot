import json
import logging
import os

from google.oauth2 import service_account
from googleapiclient.discovery import build

logger = logging.getLogger("uvicorn.error")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

SPREADSHEET_ID = os.getenv("GOOGLE_SHEET_ID")
SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "Лист1")


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


def append_booking_row(row: list):
    service = _get_service()

    result = service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A1",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
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
                valueInputOption="USER_ENTERED",
                body={"values": [[new_status]]},
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
                    "valueInputOption": "USER_ENTERED",
                    "data": [
                        {
                            "range": f"{SHEET_NAME}!B{row_index}:C{row_index}",
                            "values": [[new_date, new_time]],
                        },
                        {
                            "range": f"{SHEET_NAME}!I{row_index}",
                            "values": [[new_status]],
                        },
                    ],
                },
            ).execute()

            logger.info("Google Sheets booking rescheduled: %s", booking_id)
            return True

    logger.warning("Google Sheets booking_id not found for reschedule: %s", booking_id)
    return False
