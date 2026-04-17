from datetime import datetime, timedelta
import os
import json

from google.oauth2 import service_account
from googleapiclient.discovery import build

from app.config import (
    WORK_START,
    WORK_END,
    SLOT_STEP_MINUTES,
    BUFFER_MINUTES,
)

# ===== GOOGLE CONFIG =====
SCOPES = ["https://www.googleapis.com/auth/calendar"]

SERVICE_ACCOUNT_INFO = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")

service = None

if SERVICE_ACCOUNT_INFO:
    try:
        creds = service_account.Credentials.from_service_account_info(
            json.loads(SERVICE_ACCOUNT_INFO),
            scopes=SCOPES,
        )
        service = build("calendar", "v3", credentials=creds)
    except Exception:
        service = None

CALENDAR_ID = os.getenv("CALENDAR_ID")


# ===== GET BUSY EVENTS =====
def get_busy_events(date_str: str):
    if not service or not CALENDAR_ID:
        return []

    start = datetime.strptime(date_str, "%Y-%m-%d")
    end = start + timedelta(days=1)

    try:
        events_result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=start.isoformat() + "Z",
            timeMax=end.isoformat() + "Z",
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = events_result.get("items", [])

        busy = []

        for event in events:
            start_time = event["start"].get("dateTime")
            end_time = event["end"].get("dateTime")

            if start_time and end_time:
                busy.append((
                    datetime.fromisoformat(start_time.replace("Z", "")),
                    datetime.fromisoformat(end_time.replace("Z", "")),
                ))

        return busy

    except Exception:
        return []


# ===== GENERATE SMART SLOTS =====
def generate_slots(date_str: str, duration_minutes: int):
    date = datetime.strptime(date_str, "%Y-%m-%d")

    busy_events = get_busy_events(date_str)

    slots = []

    current = date.replace(hour=WORK_START, minute=0, second=0, microsecond=0)
    end_day = date.replace(hour=WORK_END, minute=0, second=0, microsecond=0)

    step = timedelta(minutes=SLOT_STEP_MINUTES)
    total_duration = timedelta(minutes=duration_minutes + BUFFER_MINUTES)

    while current + total_duration <= end_day:
        is_free = True

        for busy_start, busy_end in busy_events:
            if not (current + total_duration <= busy_start or current >= busy_end):
                is_free = False
                break

        if is_free:
            slots.append(current.strftime("%H:%M"))

        current += step

    return slots


# ===== CREATE EVENT =====
def create_event(name, service_name, date, time, duration):
    if not service or not CALENDAR_ID:
        return None

    try:
        start_dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        end_dt = start_dt + timedelta(minutes=duration)

        event = {
            "summary": f"💅 {service_name}",
            "description": f"Клиент: {name}",
            "start": {"dateTime": start_dt.isoformat()},
            "end": {"dateTime": end_dt.isoformat()},
        }

        created_event = service.events().insert(
            calendarId=CALENDAR_ID,
            body=event,
        ).execute()

        return created_event.get("id")

    except Exception:
        return None


# ===== DELETE EVENT =====
def delete_event(event_id):
    if not service or not CALENDAR_ID or not event_id:
        return

    try:
        service.events().delete(
            calendarId=CALENDAR_ID,
            eventId=event_id,
        ).execute()
    except Exception:
        pass


# ===== UPDATE EVENT =====
def update_event(event_id, date, time, duration):
    if not service or not CALENDAR_ID or not event_id:
        return

    try:
        start_dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        end_dt = start_dt + timedelta(minutes=duration)

        event = service.events().get(
            calendarId=CALENDAR_ID,
            eventId=event_id,
        ).execute()

        event["start"]["dateTime"] = start_dt.isoformat()
        event["end"]["dateTime"] = end_dt.isoformat()

        service.events().update(
            calendarId=CALENDAR_ID,
            eventId=event_id,
            body=event,
        ).execute()

    except Exception:
        pass
