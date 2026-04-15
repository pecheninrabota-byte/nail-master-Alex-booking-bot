from datetime import datetime, timedelta

from app.config import WORK_START, WORK_END, SLOT_STEP_MINUTES, BUFFER_MINUTES


def generate_slots(date_str: str, duration_minutes: int):
    date = datetime.strptime(date_str, "%Y-%m-%d")

    slots = []
    current = date.replace(hour=WORK_START, minute=0, second=0, microsecond=0)
    end_day = date.replace(hour=WORK_END, minute=0, second=0, microsecond=0)

    step = timedelta(minutes=SLOT_STEP_MINUTES)
    total_duration = timedelta(minutes=duration_minutes + BUFFER_MINUTES)

    while current + total_duration <= end_day:
        slots.append(current.strftime("%H:%M"))
        current += step

    return slots


def create_event_mock(data: dict, service: dict):
    return {
        "status": "confirmed",
        "message": "Тестовая запись создана. Пока без Google Calendar.",
        "booking": {
            "client_name": data["name"],
            "contact": data["contact"],
            "service": service["name"],
            "date": data["date"],
            "time": data["time"],
            "comment": data.get("comment")
        }
    }
