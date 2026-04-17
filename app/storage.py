from __future__ import annotations

from datetime import datetime
from uuid import uuid4


CLIENTS: list[dict] = []
LEADS: list[dict] = []
BOOKINGS: list[dict] = []


def now_iso() -> str:
    return datetime.utcnow().isoformat()


def create_client(name: str, contact: str, preferred_contact_method: str | None = None) -> dict:
    existing = find_client_by_contact(contact)

    if existing:
        existing["name"] = name or existing["name"]
        if preferred_contact_method:
            existing["preferred_contact_method"] = preferred_contact_method
        existing["updated_at"] = now_iso()
        return existing

    client = {
        "id": str(uuid4()),
        "name": name,
        "contact": contact,
        "preferred_contact_method": preferred_contact_method,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    CLIENTS.append(client)
    return client


def find_client_by_contact(contact: str) -> dict | None:
    for client in CLIENTS:
        if client["contact"].strip().lower() == contact.strip().lower():
            return client
    return None


def create_lead(
    client_id: str,
    lead_type: str,
    status: str,
    comment: str | None = None,
    service_id: str | None = None,
    recommended_services: list[str] | None = None,
    preferred_date: str | None = None,
    preferred_time: str | None = None,
    cancel_reason: str | None = None,
) -> dict:
    lead = {
        "id": str(uuid4()),
        "client_id": client_id,
        "lead_type": lead_type,
        "status": status,
        "comment": comment,
        "service_id": service_id,
        "recommended_services": recommended_services or [],
        "preferred_date": preferred_date,
        "preferred_time": preferred_time,
        "cancel_reason": cancel_reason,
        "source": "website_bot",
        "created_at": now_iso(),
    }
    LEADS.append(lead)
    return lead


def create_booking(
    client_id: str,
    service_id: str,
    date: str,
    time: str,
    duration_minutes: int,
    buffer_minutes: int,
    comment: str | None = None,
) -> dict:
    booking = {
        "id": str(uuid4()),
        "client_id": client_id,
        "service_id": service_id,
        "date": date,
        "time": time,
        "duration_minutes": duration_minutes,
        "buffer_minutes": buffer_minutes,
        "status": "confirmed",
        "comment": comment,
        "google_calendar_event_id": None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    BOOKINGS.append(booking)
    return booking


def find_booking_by_id(booking_id: str) -> dict | None:
    for booking in BOOKINGS:
        if booking["id"] == booking_id:
            return booking
    return None


def find_active_booking_by_name_and_contact(name: str, contact: str) -> dict | None:
    client = find_client_by_contact(contact)
    if not client:
        return None

    normalized_name = name.strip().lower()

    if client["name"].strip().lower() != normalized_name:
        return None

    for booking in reversed(BOOKINGS):
        if booking["client_id"] == client["id"] and booking["status"] == "confirmed":
            return booking

    return None


def cancel_booking(booking_id: str, reason: str | None = None) -> dict | None:
    booking = find_booking_by_id(booking_id)
    if not booking:
        return None

    booking["status"] = "cancelled"
    booking["cancel_reason"] = reason
    booking["updated_at"] = now_iso()
    return booking


def reschedule_booking(booking_id: str, new_date: str, new_time: str) -> dict | None:
    booking = find_booking_by_id(booking_id)
    if not booking:
        return None

    booking["date"] = new_date
    booking["time"] = new_time
    booking["status"] = "rescheduled"
    booking["updated_at"] = now_iso()
    return booking
