from datetime import datetime

from app.db import SessionLocal
from app.models import Client, Lead, Booking


SPECIAL_MANUAL_STATUSES = {"left", "claim", "blacklist"}


def get_db():
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _get_client_active_bookings_count(db, client_id: str) -> int:
    return (
        db.query(Booking)
        .filter(
            Booking.client_id == client_id,
            Booking.status != "cancelled",
        )
        .count()
    )


def _recalculate_client_status(db, client: Client):
    if client.is_blacklisted:
        client.client_status = "blacklist"
        return

    if client.client_status in {"left", "claim"}:
        return

    visits_count = _get_client_active_bookings_count(db, client.id)
    client.visits_count = visits_count

    if visits_count <= 1:
        client.client_status = "new"
    elif visits_count == 2:
        client.client_status = "returned"
    else:
        client.client_status = "regular"


def get_client_by_id(client_id: str):
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    db = SessionLocal()
    try:
        return db.query(Client).filter(Client.id == client_id).first()
    finally:
        db.close()


def get_client_by_contact(contact: str):
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    db = SessionLocal()
    try:
        return db.query(Client).filter(Client.contact == contact).first()
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

            _recalculate_client_status(db, client)

            db.commit()
            db.refresh(client)
            return client

        client = Client(
            name=name,
            contact=contact,
            preferred_contact_method=preferred_contact_method,
            client_status="new",
            visits_count=0,
            is_blacklisted=False,
            blacklist_reason=None,
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


def create_booking(
    client_id: str,
    data,
    duration: int,
    buffer_minutes: int,
    event_id: str | None = None,
    service: dict | None = None,
    client: Client | None = None,
):
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    db = SessionLocal()
    try:
        db_client = db.query(Client).filter(Client.id == client_id).first()

        if not db_client:
            raise RuntimeError("Client not found for booking creation")

        booking = Booking(
            client_id=client_id,
            service_id=data.service_id,
            service_name=service["name"] if service else None,
            price=service["price"] if service else None,
            date=data.preferred_date,
            time=data.preferred_time,
            duration_minutes=duration,
            buffer_minutes=buffer_minutes,
            status="confirmed",
            comment=data.comment,
            client_name=db_client.name,
            client_contact=db_client.contact,
            preferred_contact_method=db_client.preferred_contact_method,
            client_status_snapshot=db_client.client_status,
            google_calendar_event_id=event_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(booking)
        db.commit()
        db.refresh(booking)

        _recalculate_client_status(db, db_client)
        booking.client_status_snapshot = db_client.client_status
        db_client.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(booking)
        db.refresh(db_client)

        return booking
    finally:
        db.close()


def get_client_active_bookings(name: str, contact: str):
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    db = SessionLocal()
    try:
        client = (
            db.query(Client)
            .filter(Client.contact == contact)
            .first()
        )

        if not client:
            return []

        bookings = (
            db.query(Booking)
            .filter(
                Booking.client_id == client.id,
                Booking.status == "confirmed",
            )
            .order_by(Booking.date.asc(), Booking.time.asc(), Booking.created_at.asc())
            .all()
        )

        return bookings
    finally:
        db.close()


def find_booking(name: str, contact: str):
    """
    Оставлено для совместимости со старым кодом.
    Возвращает последнюю активную запись, если вдруг где-то ещё используется.
    """
    bookings = get_client_active_bookings(name=name, contact=contact)
    if not bookings:
        return None
    return bookings[-1]


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

        client = db.query(Client).filter(Client.id == booking.client_id).first()
        if client:
            _recalculate_client_status(db, client)
            client.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(booking)
        if client:
            db.refresh(client)

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
        booking.status = "confirmed"
        booking.updated_at = datetime.utcnow()

        client = db.query(Client).filter(Client.id == booking.client_id).first()
        if client:
            _recalculate_client_status(db, client)
            booking.client_status_snapshot = client.client_status
            booking.client_name = client.name
            booking.client_contact = client.contact
            booking.preferred_contact_method = client.preferred_contact_method
            client.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(booking)
        if client:
            db.refresh(client)

        return booking
    finally:
        db.close()


def is_client_blacklisted(contact: str) -> bool:
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    db = SessionLocal()
    try:
        client = db.query(Client).filter(Client.contact == contact).first()
        if not client:
            return False
        return bool(client.is_blacklisted)
    finally:
        db.close()


def set_client_blacklist(contact: str, blacklist_reason: str | None = None):
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    db = SessionLocal()
    try:
        client = db.query(Client).filter(Client.contact == contact).first()
        if not client:
            return None

        client.is_blacklisted = True
        client.blacklist_reason = blacklist_reason
        client.client_status = "blacklist"
        client.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(client)
        return client
    finally:
        db.close()


def remove_client_blacklist(contact: str):
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    db = SessionLocal()
    try:
        client = db.query(Client).filter(Client.contact == contact).first()
        if not client:
            return None

        client.is_blacklisted = False
        client.blacklist_reason = None
        _recalculate_client_status(db, client)
        client.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(client)
        return client
    finally:
        db.close()
