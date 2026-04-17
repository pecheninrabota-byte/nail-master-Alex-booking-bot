from datetime import datetime, timedelta
import os
import json

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]

SERVICE_ACCOUNT_INFO = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")

service = None

if SERVICE_ACCOUNT_INFO:
    creds = service_account.Credentials.from_service_account_info(
        json.loads(SERVICE_ACCOUNT_INFO),
        scopes=SCOPES
    )
    service = build("calendar", "v3", credentials=creds)

CALENDAR_ID = os.getenv("CALENDAR_ID")


def create_event(name, service_name, date, time, duration):
    if not service:
        return None

    start_dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
    end_dt = start_dt + timedelta(minutes=duration)

    event = {
        "summary": f"💅 {service_name}",
        "description": f"Клиент: {name}",
        "start": {"dateTime": start_dt.isoformat()},
        "end": {"dateTime": end_dt.isoformat()},
    }

    created = service.events().insert(
        calendarId=CALENDAR_ID,
        body=event
    ).execute()

    return created.get("id")


def delete_event(event_id):
    if not service or not event_id:
        return

    try:
        service.events().delete(
            calendarId=CALENDAR_ID,
            eventId=event_id
        ).execute()
    except:
        pass


def update_event(event_id, date, time, duration):
    if not service or not event_id:
        return

    start_dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
    end_dt = start_dt + timedelta(minutes=duration)

    try:
        event = service.events().get(
            calendarId=CALENDAR_ID,
            eventId=event_id
        ).execute()

        event["start"]["dateTime"] = start_dt.isoformat()
        event["end"]["dateTime"] = end_dt.isoformat()

        service.events().update(
            calendarId=CALENDAR_ID,
            eventId=event_id,
            body=event
        ).execute()
    except:
        pass
