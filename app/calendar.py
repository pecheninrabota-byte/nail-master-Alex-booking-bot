import json
import logging
import os
from datetime import datetime, timedelta, time
from typing import List, Optional
from zoneinfo import ZoneInfo

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
MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def _get_google_credentials():
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
    naive_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    return naive_dt.replace(tzinfo=MOSCOW_TZ)


def _now_local() -> datetime:
    return datetime.now(MOSCOW_TZ)


def _event_time_range(date_str: str, time_str: str, duration_minutes: int):
    start_dt = _parse_datetime(date_str, time_str)
    end_dt = start_dt + timedelta(minutes=duration_minutes)

    return start_dt, end_dt


def generate_slots(date_str: str, duration_minutes: int) -> List[str]:
    """
    Возвращает свободные слоты HH:MM для конкретной даты.
    Учитывает:
    - рабочее время
    - длительность услуги
    - буфер 30 минут после услуги
    - уже созданные события в календаре
    - прошедшее время на сегодня
    """
    service = _get_calendar_service()

    day = _parse_date(date_str).date()
    day_start = datetime.combine(day, time(hour=WORK_START, minute=0), tzinfo=MOSCOW_TZ)
    day_end = datetime.combine(day, time(hour=WORK_END, minute=0), tzinfo=MOSCOW_TZ)

    events_result = (
        service.events()
        .list(
            calendarId=CALENDAR_ID,
            timeMin=day_start.isoformat(),
            timeMax=day_end.isoformat(),
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
            start_dt = datetime.fromisoformat(start_raw)
            end_dt = datetime.fromisoformat(end_raw)

            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=MOSCOW_TZ)
            else:
                start_dt = start_dt.astimezone(MOSCOW_TZ)

            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=MOSCOW_TZ)
            else:
                end_dt = end_dt.astimezone(MOSCOW_TZ)

            busy_ranges.append((start_dt, end_dt))
        except Exception:
            logger.exception("Failed to parse event datetime: %s", event)

    slots = []
    current = day_start
    now = _now_local()

    while current < day_end:
        slot_start = current
        slot_end = current + timedelta(minutes=duration_minutes + BUFFER_MINUTES)

        if slot_end > day_end:
            break

        if day == now.date() and slot_start <= now:
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
    contact: str,
    service_name: str,
    date: str,
    time: str,
    duration: int,
    preferred_contact_method: Optional[str] = None,
    comment: Optional[str] = None,
    action_label: str = "Новая запись",
) -> str:
    service = _get_calendar_service()
    start_dt, end_dt = _event_time_range(date, time, duration)

    description_parts = [
        f"Действие: {action_label}",
        f"Клиент: {name}",
        f"Контакт: {contact}",
        f"Услуга: {service_name}",
        f"Дата: {date}",
        f"Время: {time}",
    ]

    if preferred_contact_method:
        description_parts.append(f"Способ связи: {preferred_contact_method}")

    if comment:
        description_parts.append(f"Комментарий: {comment}")

    event_body = {
        "summary": f"{service_name} — {name}",
        "description": "\n".join(description_parts),
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": "Europe/Moscow",
        },
        "end": {
            "dateTime": end_dt.isoformat(),
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
        "Google Calendar event created: event_id=%s client=%s service=%s date=%s time=%s",
        event_id,
        name,
        service_name,
        date,
        time,
    )

    return event_id


def delete_event(event_id: str) -> bool:
    if not event_id:
        logger.warning("delete_event called without event_id")
        return False

    service = _get_calendar_service()
    service.events().delete(calendarId=CALENDAR_ID, eventId=event_id).execute()

    logger.info("Google Calendar event deleted: event_id=%s", event_id)
    return True


def update_event(
    event_id: str,
    date: str,
    time: str,
    duration: int,
    name: Optional[str] = None,
    contact: Optional[str] = None,
    service_name: Optional[str] = None,
    preferred_contact_method: Optional[str] = None,
    comment: Optional[str] = None,
    action_label: str = "Перенос записи",
) -> bool:
    if not event_id:
        logger.warning("update_event called without event_id")
        return False

    service = _get_calendar_service()

    event = service.events().get(
        calendarId=CALENDAR_ID,
        eventId=event_id
    ).execute()

    start_dt, end_dt = _event_time_range(date, time, duration)

    event["start"] = {
        "dateTime": start_dt.isoformat(),
        "timeZone": "Europe/Moscow",
    }
    event["end"] = {
        "dateTime": end_dt.isoformat(),
        "timeZone": "Europe/Moscow",
    }

    if service_name and name:
        event["summary"] = f"{service_name} — {name}"

    description_parts = [f"Действие: {action_label}"]

    if name:
        description_parts.append(f"Клиент: {name}")
    if contact:
        description_parts.append(f"Контакт: {contact}")
    if service_name:
        description_parts.append(f"Услуга: {service_name}")

    description_parts.append(f"Дата: {date}")
    description_parts.append(f"Время: {time}")

    if preferred_contact_method:
        description_parts.append(f"Способ связи: {preferred_contact_method}")
    if comment:
        description_parts.append(f"Комментарий: {comment}")

    event["description"] = "\n".join(description_parts)

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
