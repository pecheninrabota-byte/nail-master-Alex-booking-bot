from datetime import datetime

from app.db import SessionLocal
from app import models


def get_db():
    if SessionLocal is None:
        return None
    return SessionLocal()


# ===== CLIENT =====
def get_or_create_client(name: str, contact: str):
    db = get_db()
    if not db:
        return None

    try:
        client = db.query(models.Client).filter(
            models.Client.contact == contact
        ).first()

        if client:
            client.name = name
            client.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(client)
            return client

        client = models.Client(
            name=name,
            contact=contact,
        )
        db.add(client)
        db.commit()
        db.refresh(client)
        return client
    finally:
        db.close()


# ===== LEAD =====
def create_lead(
    client_id: str,
    lead_type: str,
    status: str,
    service_id: str = None,
    preferred_date: str = None,
    preferred_time: str = None,
    comment: str = None,
    cancel_reason: str = None,
    source: str = "website_bot",
):
    db = get_db()
    if not db:
        return None

    try:
        lead = models.Lead(
            client_id=client_id,
            lead_type=lead_type,
            status=status,
            service_id=service_id,
            preferred_date=preferred_date,
            preferred_time=preferred_time,
            comment=comment,
            cancel_reason=cancel_reason,
            source=source,
        )
        db.add(lead)
        db.commit()
        db.refresh(lead)
        return lead
    finally:
        db.close()


# ===== BOOKING =====
def create_booking(
    client_id: str,
    data,
    duration: int,
    buffer_minutes: int,
    event_id: str = None,
):
    db = get_db()
    if not db:
        return None

    try:
        booking = models.Booking(
            client_id=client_id,
            service_id=data.service_id,
            date=data.preferred_date,
            time=data.preferred_time,
            duration_minutes=duration,
            buffer_minutes=buffer_minutes,
            comment=data.comment,
            status="confirmed",
            google_calendar_event_id=event_id,
            updated_at=datetime.utcnow(),
        )
        db.add(booking)
        db.commit()
        db.refresh(booking)
        return booking
    finally:
        db.close()


def find_booking(name: str, contact: str):
    db = get_db()
    if not db:
        return None

    try:
        booking = (
            db.query(models.Booking)
            .join(models.Client, models.Booking.client_id == models.Client.id)
            .filter(
                models.Client.name == name,
                models.Client.contact == contact,
                models.Booking.status.in_(["confirmed", "rescheduled"]),
            )
            .order_by(models.Booking.created_at.desc())
            .first()
        )
        return booking
    finally:
        db.close()


def find_booking_by_id(booking_id: str):
    db = get_db()
    if not db:
        return None

    try:
        booking = (
            db.query(models.Booking)
            .filter(models.Booking.id == booking_id)
            .first()
        )
        return booking
    finally:
        db.close()


def cancel_booking(booking_id: str, reason: str = None):
    db = get_db()
    if not db:
        return None

    try:
        booking = (
            db.query(models.Booking)
            .filter(models.Booking.id == booking_id)
            .first()
        )

        if not booking:
            return None

        booking.status = "cancelled"
        booking.updated_at = datetime.utcnow()

        if reason:
            if booking.comment:
                booking.comment = f"{booking.comment}\nПричина отмены: {reason}"
            else:
                booking.comment = f"Причина отмены: {reason}"

        db.commit()
        db.refresh(booking)
        return booking
    finally:
        db.close()


def reschedule_booking(booking_id: str, new_date: str, new_time: str):
    db = get_db()
    if not db:
        return None

    try:
        booking = (
            db.query(models.Booking)
            .filter(models.Booking.id == booking_id)
            .first()
        )

        if not booking:
            return None

        booking.date = new_date
        booking.time = new_time
        booking.status = "rescheduled"
        booking.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(booking)
        return booking
    finally:
        db.close()
