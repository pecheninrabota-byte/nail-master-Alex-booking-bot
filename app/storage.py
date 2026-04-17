from datetime import datetime

from app.db import SessionLocal
from app.models import Booking, Client, Lead


def create_client(name: str, contact: str, preferred_contact_method: str | None = None) -> dict:
    db = SessionLocal()
    try:
        client = db.query(Client).filter(Client.contact == contact).first()

        if client:
            client.name = name or client.name
            if preferred_contact_method:
                client.preferred_contact_method = preferred_contact_method
            client.updated_at = datetime.utcnow()
        else:
            client = Client(
                name=name,
                contact=contact,
                preferred_contact_method=preferred_contact_method,
            )
            db.add(client)

        db.commit()
        db.refresh(client)

        return {
            "id": client.id,
            "name": client.name,
            "contact": client.contact,
            "preferred_contact_method": client.preferred_contact_method,
            "created_at": client.created_at.isoformat(),
            "updated_at": client.updated_at.isoformat(),
        }
    finally:
        db.close()


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
    db = SessionLocal()
    try:
        lead = Lead(
            client_id=client_id,
            lead_type=lead_type,
            status=status,
            service_id=service_id,
            preferred_date=preferred_date,
            preferred_time=preferred_time,
            comment=comment,
            cancel_reason=cancel_reason,
            source="website_bot",
        )
        db.add(lead)
        db.commit()
        db.refresh(lead)

        return {
            "id": lead.id,
            "client_id": lead.client_id,
            "lead_type": lead.lead_type,
            "status": lead.status,
            "service_id": lead.service_id,
            "preferred_date": lead.preferred_date,
            "preferred_time": lead.preferred_time,
            "comment": lead.comment,
            "cancel_reason": lead.cancel_reason,
            "created_at": lead.created_at.isoformat(),
        }
    finally:
        db.close()


def create_booking(
    client_id: str,
    service_id: str,
    date: str,
    time: str,
    duration_minutes: int,
    buffer_minutes: int,
    comment: str | None = None,
) -> dict:
    db = SessionLocal()
    try:
        booking = Booking(
            client_id=client_id,
            service_id=service_id,
            date=date,
            time=time,
            duration_minutes=duration_minutes,
            buffer_minutes=buffer_minutes,
            comment=comment,
            status="confirmed",
        )
        db.add(booking)
        db.commit()
        db.refresh(booking)

        return {
            "id": booking.id,
            "client_id": booking.client_id,
            "service_id": booking.service_id,
            "date": booking.date,
            "time": booking.time,
            "duration_minutes": booking.duration_minutes,
            "buffer_minutes": booking.buffer_minutes,
            "status": booking.status,
            "comment": booking.comment,
            "created_at": booking.created_at.isoformat(),
            "updated_at": booking.updated_at.isoformat(),
        }
    finally:
        db.close()


def find_booking_by_id(booking_id: str) -> dict | None:
    db = SessionLocal()
    try:
        booking = db.query(Booking).filter(Booking.id == booking_id).first()
        if not booking:
            return None

        return {
            "id": booking.id,
            "client_id": booking.client_id,
            "service_id": booking.service_id,
            "date": booking.date,
            "time": booking.time,
            "duration_minutes": booking.duration_minutes,
            "buffer_minutes": booking.buffer_minutes,
            "status": booking.status,
            "comment": booking.comment,
            "google_calendar_event_id": booking.google_calendar_event_id,
            "created_at": booking.created_at.isoformat(),
            "updated_at": booking.updated_at.isoformat(),
        }
    finally:
        db.close()


def find_active_booking_by_name_and_contact(name: str, contact: str) -> dict | None:
    db = SessionLocal()
    try:
        client = db.query(Client).filter(Client.contact == contact).first()
        if not client:
            return None

        if client.name.strip().lower() != name.strip().lower():
            return None

        booking = (
            db.query(Booking)
            .filter(Booking.client_id == client.id, Booking.status == "confirmed")
            .order_by(Booking.created_at.desc())
            .first()
        )

        if not booking:
            return None

        return {
            "id": booking.id,
            "client_id": booking.client_id,
            "service_id": booking.service_id,
            "date": booking.date,
            "time": booking.time,
            "duration_minutes": booking.duration_minutes,
            "buffer_minutes": booking.buffer_minutes,
            "status": booking.status,
            "comment": booking.comment,
            "google_calendar_event_id": booking.google_calendar_event_id,
            "created_at": booking.created_at.isoformat(),
            "updated_at": booking.updated_at.isoformat(),
        }
    finally:
        db.close()


def cancel_booking(booking_id: str, reason: str | None = None) -> dict | None:
    db = SessionLocal()
    try:
        booking = db.query(Booking).filter(Booking.id == booking_id).first()
        if not booking:
            return None

        booking.status = "cancelled"
        booking.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(booking)

        return {
            "id": booking.id,
            "client_id": booking.client_id,
            "service_id": booking.service_id,
            "date": booking.date,
            "time": booking.time,
            "duration_minutes": booking.duration_minutes,
            "buffer_minutes": booking.buffer_minutes,
            "status": booking.status,
            "comment": booking.comment,
            "google_calendar_event_id": booking.google_calendar_event_id,
            "created_at": booking.created_at.isoformat(),
            "updated_at": booking.updated_at.isoformat(),
            "cancel_reason": reason,
        }
    finally:
        db.close()


def reschedule_booking(booking_id: str, new_date: str, new_time: str) -> dict | None:
    db = SessionLocal()
    try:
        booking = db.query(Booking).filter(Booking.id == booking_id).first()
        if not booking:
            return None

        booking.date = new_date
        booking.time = new_time
        booking.status = "rescheduled"
        booking.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(booking)

        return {
            "id": booking.id,
            "client_id": booking.client_id,
            "service_id": booking.service_id,
            "date": booking.date,
            "time": booking.time,
            "duration_minutes": booking.duration_minutes,
            "buffer_minutes": booking.buffer_minutes,
            "status": booking.status,
            "comment": booking.comment,
            "google_calendar_event_id": booking.google_calendar_event_id,
            "created_at": booking.created_at.isoformat(),
            "updated_at": booking.updated_at.isoformat(),
        }
    finally:
        db.close()
