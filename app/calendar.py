import json
import logging
import os
from datetime import datetime, timedelta, time
from typing import List, Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build

from app.config import (
    WORK_START,
    WORK_END,
    SLOT_STEP_MINUTES,
    BUFFER_MINUTES,
    CALENDAR_ID,
)

logger = logging.getLogger("uvicorn.error")

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _get_google_credentials():
    """
    Берёт service account JSON из переменной окружения GOOGLE_SERVICE_ACCOUNT_JSON.
    В Railway это удобно хранить как одну длинную JSON-строку.
    """
    raw_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")

    if not raw_json:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON is missing")

    try:
        info = json.loads(raw_json)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid GOOGLE_SERVICE_ACCOUNT_JSON: {e}")

    return service_account.Credentials.from_service_account_info(
        info,
        scopes=SCOPES,
    )


def _get_calendar_service():
    credentials = _get_google_credentials()
    return build("calendar", "v3", credentials=credentials)


def _parse_date(date_str: str) -> datetime:
    return datetime.strptime(date_str, "%Y-%m-%d")


def _parse_datetime(date_str: str, time_str: str) -> datetime:
    return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")


def _now_local() -> datetime:
    """
    Пока без timezone-обвязки.
    Для текущего проекта этого достаточно, если Railway и логика даты совпадают с ожидаемым часовым поясом.
    Если позже понадобится, переведём на zoneinfo.
    """
    return datetime.now()


def _event_time_range(date_str: str, time_str: str, duration_minutes: int):
    start_dt = _parse_datetime(date_str, time_str)
    end_dt = start_dt + timedelta(minutes=duration_minutes)

    return (
        start_dt.isoformat(),
        end_dt.isoformat(),
    )


def _buffered_end(date_str: str, time_str: str, duration_minutes: int) -> datetime:
    start_dt = _parse_datetime(date_str, time_str)
    return start_dt + timedelta(minutes=duration_minutes + BUFFER_MINUTES)


def generate_slots(date_str: str, duration_minutes: int) -> List[str]:
    """
    Возвращает список доступных слотов HH:MM на конкретную дату.
    Учитывает:
    - рабочие часы
    - длительность услуги
    - буфер после услуги
    - уже существующие события в Google Calendar
    - прошедшее время на сегодня
    """
    service = _get_calendar_service()

    day = _parse_date(date_str)
    day_start = datetime.combine(day.date(), time(hour=WORK_START, minute=0))
    day_end = datetime.combine(day.date(), time(hour=WORK_END, minute=0))

    # Забираем события за день
    events_result = (
        service.events()
        .list(
            calendarId=CALENDAR_ID,
            timeMin=day_start.isoformat() + "Z",
            timeMax=day_end.isoformat() + "Z",
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    items = events_result.get("items", [])

    busy_ranges = []
    for event in items:
        start_raw = event.get("start", {}).get("dateTime")
        end_raw = event.get("end", {}).get("dateTime")

        if not start_raw or not end_raw:
            continue

        try:
            start_dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00")).replace(tzinfo=None)
            end_dt = datetime.fromisoformat(end_raw.replace("Z", "+00:00")).replace(tzinfo=None)
            busy_ranges.append((start_dt, end_dt))
        except Exception:
            logger.exception("Failed to parse Google event datetime: %s", event)

    slots = []
    current = day_start
    now = _now_local()

    while current < day_end:
        slot_start = current
        slot_end = current + timedelta(minutes=duration_minutes + BUFFER_MINUTES)

        # слот должен полностью помещаться в рабочий день
        if slot_end > day_end:
            break

        # нельзя показывать прошедшее время на сегодня
        if day.date() == now.date() and slot_start <= now:
            current += timedelta(minutes=SLOT_STEP_MINUTES)
            continue

        intersects = False
        for busy_start, busy_end in busy_ranges:
            if slot_start < busy_end and slot_end > busy_start:
                intersects = True
                break

        if not intersects:
            slots.append(slot_start.strftime("%H:%M"))

        current += timedelta(minutes=SLOT_STEP_MINUTES)

    logger.info(
        "Generated slots for date=%s duration=%s -> %s",
        date_str,
        duration_minutes,
        slots,
    )

    return slots


def create_event(
    name: str,
    service_name: str,
    date: str,
    time: str,
    duration: int,
    contact: Optional[str] = None,
    comment: Optional[str] = None,
) -> str:
    service = _get_calendar_service()
    start_iso, end_iso = _event_time_range(date, time, duration)

    description_parts = [f"Клиент: {name}"]
    if contact:
        description_parts.append(f"Контакт: {contact}")
    if comment:
        description_parts.append(f"Комментарий: {comment}")

    event_body = {
        "summary": f"{service_name} — {name}",
        "description": "\n".join(description_parts),
        "start": {
            "dateTime": start_iso,
            "timeZone": "Europe/Moscow",
        },
        "end": {
            "dateTime": end_iso,
            "timeZone": "Europe/Moscow",
        },
    }

    created_event = (
        service.events()
        .insert(calendarId=CALENDAR_ID, body=event_body)
        .execute()
    )

    event_id = created_event["id"]
    logger.info(
        "Google Calendar event created: event_id=%s date=%s time=%s service=%s client=%s",
        event_id,
        date,
        time,
        service_name,
        name,
    )
    return event_id


def delete_event(event_id: str) -> bool:
    if not event_id:
        logger.warning("delete_event called without event_id")
        return False

    service = _get_calendar_service()

    service.events().delete(
        calendarId=CALENDAR_ID,
        eventId=event_id
    ).execute()

    logger.info("Google Calendar event deleted: event_id=%s", event_id)
    return True


def update_event(event_id: str, date: str, time: str, duration: int) -> bool:
    if not event_id:
        logger.warning("update_event called without event_id")
        return False

    service = _get_calendar_service()
    event = service.events().get(
        calendarId=CALENDAR_ID,
        eventId=event_id
    ).execute()

    start_iso, end_iso = _event_time_range(date, time, duration)

    event["start"] = {
        "dateTime": start_iso,
        "timeZone": "Europe/Moscow",
    }
    event["end"] = {
        "dateTime": end_iso,
        "timeZone": "Europe/Moscow",
    }

    service.events().update(
        calendarId=CALENDAR_ID,
        eventId=event_id,
        body=event
    ).execute()

    logger.info(
        "Google Calendar event updated: event_id=%s new_date=%s new_time=%s",
        event_id,
        date,
        time,
    )
    return True
