from datetime import datetime
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from app.db import Base


def gen_id() -> str:
    return str(uuid.uuid4())


class Client(Base):
    __tablename__ = "clients"

    id = Column(String, primary_key=True, default=gen_id)
    name = Column(String, nullable=False)
    contact = Column(String, nullable=False, index=True, unique=False)
    preferred_contact_method = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(String, primary_key=True, default=gen_id)
    client_id = Column(String, ForeignKey("clients.id"), nullable=False, index=True)

    service_id = Column(String, nullable=False)
    date = Column(String, nullable=False)
    time = Column(String, nullable=False)

    duration_minutes = Column(Integer, nullable=False)
    buffer_minutes = Column(Integer, nullable=False)

    status = Column(String, default="confirmed", nullable=False)
    comment = Column(Text, nullable=True)
    google_calendar_event_id = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Lead(Base):
    __tablename__ = "leads"

    id = Column(String, primary_key=True, default=gen_id)
    client_id = Column(String, ForeignKey("clients.id"), nullable=False, index=True)

    lead_type = Column(String, nullable=False)
    status = Column(String, nullable=False)

    service_id = Column(String, nullable=True)
    preferred_date = Column(String, nullable=True)
    preferred_time = Column(String, nullable=True)

    comment = Column(Text, nullable=True)
    cancel_reason = Column(Text, nullable=True)
    source = Column(String, default="website_bot", nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
