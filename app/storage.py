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

    client = db.query(models.Client).filter(
        models.Client.contact == contact
    ).first()

    if client:
        db.close()
        return client

    client = models.Client(name=name, contact=contact)
    db.add(client)
    db.commit()
    db.refresh(client)
    db.close()
    return client


# ===== LEAD =====
def create_lead(client_id: str, lead_type: str, status: str, **kwargs):
    db = get_db()
    if not db:
        return None

    lead = models.Lead(
        client_id=client_id,
        lead_type=lead_type,
        status=status,
        **kwargs
    )

    db.add(lead)
    db.commit()
    db.refresh(lead)
    db.close()
    return lead


# ===== BOOKING =====
def create_booking(client_id: str, data, duration: int, buffer_minutes: int, event_id: str):
    db = get_db()
    if not db:
        return None

    booking = models.Booking(
        client_id=client_id,
        service_id=data.service_id,
        date=data.preferred_date,
        time=data.preferred_time,
        duration_minutes=duration,
        buffer_minutes=buffer_minutes,
        comment=data.comment,
        google_calendar_event_id=event_id
    )

    db.add(booking)
    db.commit()
    db.refresh(booking)
    db.close()
    return booking


def find_booking(name: str, contact: str):
    db = get_db()
    if not db:
        return None

    booking = db.query(models.Booking).join(models.Client).filter(
        models.Client.name == name,
        models.Client.contact == contact,
        models.Booking.status == "confirmed"
    ).first()

    db.close()
    return booking


def cancel_booking(booking_id: str, reason: str):
    db = get_db()
    if not db:
        return None

    booking = db.query(models.Booking).filter(
        models.Booking.id == booking_id
    ).first()

    if not booking:
        db.close()
        return None

    booking.status = "cancelled"

    db.commit()
    db.refresh(booking)
    db.close()
    return booking


def reschedule_booking(booking_id: str, new_date: str, new_time: str):
    db = get_db()
    if not db:
        return None

    booking = db.query(models.Booking).filter(
        models.Booking.id == booking_id
    ).first()

    if not booking:
        db.close()
        return None

    booking.date = new_date
    booking.time = new_time
    booking.status = "rescheduled"

    db.commit()
    db.refresh(booking)
    db.close()
    return booking
