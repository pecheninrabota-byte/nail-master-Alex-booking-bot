from datetime import datetime

from sqlalchemy import and_

from app.db import SessionLocal
from app.models import Booking, Client, Lead


def _db_required():
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is missing or database is not configured")


def _normalize_contact(contact: str) -> str:
    return (contact or "").strip().lower()


def get_or_create_client(name: str, contact: str, preferred_contact_method: str | None = None):
    _db_required()

    db = SessionLocal()
    try:
        normalized_contact = _normalize_contact(contact)

        client = (
            db.query(Client)
            .filter(Client.contact == normalized_contact)
            .first()
        )

        if client:
            client.name = name
            if preferred_contact_method:
                client.preferred_contact_method = preferred_contact_method
            client.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(client)
            return client

        client = Client(
            name=name,
            contact=normalized_contact,
            preferred_contact_method=preferred_contact_method,
            client_status="new",
            visits_count=0,
            is_blacklisted=False,
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
    service_id: str | None = None,
    preferred_date: str | None = None,
    preferred_time: str | None = None,
    comment: str | None = None,
    cancel_reason: str | None = None,
):
    _db_required()

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
        return lead
    finally:
        db.close()


def create_booking(
    client_id: str,
    data,
    duration: int,
    buffer_minutes: int,
    event_id: str | None,
    service: dict,
    client,
):
    _db_required()

    db = SessionLocal()
    try:
        booking = Booking(
            client_id=client_id,
            service_id=service["id"],
            service_name=service.get("name"),
            price=service.get("price"),
            date=data.preferred_date,
            time=data.preferred_time,
            duration_minutes=duration,
            buffer_minutes=buffer_minutes,
            status="confirmed",
            comment=data.comment,
            client_name=data.name,
            client_contact=_normalize_contact(data.contact),
            preferred_contact_method=data.preferred_contact_method,
            client_status_snapshot=client.client_status,
            google_calendar_event_id=event_id,
        )

        db.add(booking)

        client_in_db = db.query(Client).filter(Client.id == client_id).first()
        if client_in_db:
            client_in_db.visits_count = (client_in_db.visits_count or 0) + 1

            if client_in_db.visits_count <= 1:
                client_in_db.client_status = "new"
            elif client_in_db.visits_count == 2:
                client_in_db.client_status = "returned"
            else:
                client_in_db.client_status = "regular"

            client_in_db.updated_at = datetime.utcnow()
            booking.client_status_snapshot = client_in_db.client_status

        db.commit()
        db.refresh(booking)
        return booking
    finally:
        db.close()


def get_client_active_bookings(name: str, contact: str):
    _db_required()

    db = SessionLocal()
    try:
        normalized_contact = _normalize_contact(contact)

        return (
            db.query(Booking)
            .filter(
                and_(
                    Booking.client_contact == normalized_contact,
                    Booking.status.in_(["confirmed", "rescheduled"]),
                )
            )
            .order_by(Booking.date.asc(), Booking.time.asc())
            .all()
        )
    finally:
        db.close()


def find_booking_by_id(booking_id: str):
    _db_required()

    db = SessionLocal()
    try:
        booking = db.query(Booking).filter(Booking.id == booking_id).first()

        if not booking:
            return None

        db.expunge(booking)
        return booking
    finally:
        db.close()


def cancel_booking(booking_id: str, reason: str | None = None):
    _db_required()

    db = SessionLocal()
    try:
        booking = db.query(Booking).filter(Booking.id == booking_id).first()

        if not booking:
            return None

        booking.status = "cancelled"
        booking.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(booking)
        db.expunge(booking)
        return booking
    finally:
        db.close()


def reschedule_booking(booking_id: str, new_date: str, new_time: str):
    _db_required()

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
        db.expunge(booking)
        return booking
    finally:
        db.close()


def is_client_blacklisted(contact: str) -> bool:
    _db_required()

    db = SessionLocal()
    try:
        normalized_contact = _normalize_contact(contact)

        client = db.query(Client).filter(Client.contact == normalized_contact).first()

        return bool(client and client.is_blacklisted)
    finally:
        db.close()


def set_client_blacklist(contact: str, reason: str | None = None):
    _db_required()

    db = SessionLocal()
    try:
        normalized_contact = _normalize_contact(contact)

        client = db.query(Client).filter(Client.contact == normalized_contact).first()

        if not client:
            client = Client(
                name="Unknown",
                contact=normalized_contact,
                client_status="blacklist",
                visits_count=0,
                is_blacklisted=True,
                blacklist_reason=reason,
            )
            db.add(client)
        else:
            client.is_blacklisted = True
            client.blacklist_reason = reason
            client.client_status = "blacklist"
            client.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(client)
        return client
    finally:
        db.close()


def remove_client_blacklist(contact: str):
    _db_required()

    db = SessionLocal()
    try:
        normalized_contact = _normalize_contact(contact)

        client = db.query(Client).filter(Client.contact == normalized_contact).first()

        if not client:
            return None

        client.is_blacklisted = False
        client.blacklist_reason = None
        if client.client_status == "blacklist":
            client.client_status = "returned" if (client.visits_count or 0) >= 2 else "new"

        client.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(client)
        return client
    finally:
        db.close()
