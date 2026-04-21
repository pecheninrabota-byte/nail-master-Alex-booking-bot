from datetime import datetime

from app.db import SessionLocal
from app.models import Client, Lead, Booking


def get_db():
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_or_create_client(name: str, contact: str, preferred_contact_method: str | None = None):
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    db = SessionLocal()
    try:
        client = db.query(Client).filter(Client.contact == contact).first()

        if client:
            client.name = name
            if preferred_contact_method is not None:
                client.preferred_contact_method = preferred_contact_method
            client.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(client)
            return client

        client = Client(
            name=name,
            contact=contact,
            preferred_contact_method=preferred_contact_method,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(client)
        db.commit()
        db.refresh(client)
        return client
    finally:
        db.close()


def create_lead(
    client_id: str,
    lead_type: str,
    status: str,
    comment: str | None = None,
    service_id: str | None = None,
    preferred_date: str | None = None,
    preferred_time: str | None = None,
    cancel_reason: str | None = None,
):
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

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
            created_at=datetime.utcnow(),
        )
        db.add(lead)
        db.commit()
        db.refresh(lead)
        return lead
    finally:
        db.close()


def create_booking(client_id: str, data, duration: int, buffer_minutes: int, event_id: str | None = None):
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    db = SessionLocal()
    try:
        booking = Booking(
            client_id=client_id,
            service_id=data.service_id,
            date=data.preferred_date,
            time=data.preferred_time,
            duration_minutes=duration,
            buffer_minutes=buffer_minutes,
            status="confirmed",
            comment=data.comment,
            google_calendar_event_id=event_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(booking)
        db.commit()
        db.refresh(booking)
        return booking
    finally:
        db.close()


def find_booking(name: str, contact: str):
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    db = SessionLocal()
    try:
        client = (
            db.query(Client)
            .filter(Client.name == name, Client.contact == contact)
            .first()
        )

        if not client:
            return None

        booking = (
            db.query(Booking)
            .filter(
                Booking.client_id == client.id,
                Booking.status == "confirmed",
            )
            .order_by(Booking.created_at.desc())
            .first()
        )

        return booking
    finally:
        db.close()


def find_booking_by_id(booking_id: str):
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    db = SessionLocal()
    try:
        return db.query(Booking).filter(Booking.id == booking_id).first()
    finally:
        db.close()


def cancel_booking(booking_id: str, reason: str | None = None):
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    db = SessionLocal()
    try:
        booking = db.query(Booking).filter(Booking.id == booking_id).first()

        if not booking:
            return None

        booking.status = "cancelled"
        booking.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(booking)
        return booking
    finally:
        db.close()


def reschedule_booking(booking_id: str, new_date: str, new_time: str):
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    db = SessionLocal()
    try:
        booking = db.query(Booking).filter(Booking.id == booking_id).first()

        if not booking:
            return None

        booking.date = new_date
        booking.time = new_time
        booking.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(booking)
        return booking
    finally:
        db.close()
