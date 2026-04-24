import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import text

from app.db import Base, engine, SessionLocal
from app.services import SERVICES, FAQ, get_service
from app.calendar import generate_slots, create_event, delete_event, update_event
from app.config import BUFFER_MINUTES
from app.logic import (
    recommend_services,
    build_booking_success_message,
    get_total_duration_with_buffer,
)
from app.schemas import (
    ServiceRecommendationRequest,
    ServiceRecommendationResponse,
    ContactRequestCreate,
    BookingLeadCreate,
    FindBookingRequest,
    CancelBookingRequest,
    RescheduleBookingRequest,
)
from app.storage import (
    get_or_create_client,
    create_lead,
    create_booking,
    find_booking_by_id,
    cancel_booking,
    reschedule_booking,
    get_client_by_id,
    get_client_active_bookings,
    is_client_blacklisted,
)
from app.telegram import (
    send_telegram_message,
    format_booking_created_message,
    format_booking_cancelled_message,
    format_booking_rescheduled_message,
    format_contact_request_message,
)
from app.sheets import (
    append_booking_row,
    update_booking_status,
)

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="Nail Master Booking Bot")

if engine is not None:
    Base.metadata.create_all(bind=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def ensure_slot_is_available(service_id: str, date: str, slot_time: str):
    service = get_service(service_id)

    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    available_slots = generate_slots(date, service["duration"])

    if slot_time not in available_slots:
        raise HTTPException(
            status_code=409,
            detail="Selected time is no longer available. Please choose another slot.",
        )

    return service, available_slots


@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "Nail Master Booking API is running",
    }


@app.get("/services")
def get_services():
    return SERVICES


@app.get("/faq")
def get_faq():
    return FAQ


@app.get("/slots")
def get_slots(service_id: str, date: str):
    service = get_service(service_id)

    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    slots = generate_slots(date, service["duration"])

    return {
        "service_id": service_id,
        "service_name": service["name"],
        "date": date,
        "duration_minutes": service["duration"],
        "buffer_minutes": BUFFER_MINUTES,
        "total_time_block_minutes": get_total_duration_with_buffer(service, BUFFER_MINUTES),
        "slots": slots,
    }


@app.post("/service-recommendation", response_model=ServiceRecommendationResponse)
def service_recommendation(data: ServiceRecommendationRequest):
    recommended_services, explanation = recommend_services(
        category=data.category,
        care_needed=data.care_needed,
        coating_type=data.coating_type,
    )

    recommended_ids = [service["id"] for service in recommended_services]

    return {
        "recommended_services": recommended_services,
        "explanation": explanation,
        "recommended_ids": recommended_ids,
    }


@app.post("/contact-request")
def create_contact_request(data: ContactRequestCreate):
    preferred_contact_method = getattr(data, "preferred_contact_method", None)

    client = get_or_create_client(
        name=data.name,
        contact=data.contact,
        preferred_contact_method=preferred_contact_method,
    )

    lead = create_lead(
        client_id=client.id,
        lead_type="contact_request",
        status="contact_request",
        comment=data.comment,
    )

    telegram_result = send_telegram_message(
        format_contact_request_message(
            client_name=data.name,
            contact=data.contact,
            preferred_contact_method=preferred_contact_method,
            comment=data.comment,
        )
    )
    logger.info("Contact request telegram result: %s", telegram_result)

    return {
        "status": "success",
        "message": "Спасибо! Александр свяжется с вами в течение суток удобным для вас способом.",
        "client_id": client.id,
        "lead_id": lead.id if lead else None,
    }


@app.post("/booking-lead")
def create_booking_lead(data: BookingLeadCreate):
    service, _ = ensure_slot_is_available(
        service_id=data.service_id,
        date=data.preferred_date,
        slot_time=data.preferred_time,
    )

    if is_client_blacklisted(data.contact):
        raise HTTPException(
            status_code=403,
            detail="Booking is not available for this client. Please contact the master directly.",
        )

    preferred_contact_method = getattr(data, "preferred_contact_method", None)

    client = get_or_create_client(
        name=data.name,
        contact=data.contact,
        preferred_contact_method=preferred_contact_method,
    )

    lead = create_lead(
        client_id=client.id,
        lead_type="booking_started",
        status="booking_started",
        comment=data.comment,
        service_id=data.service_id,
        preferred_date=data.preferred_date,
        preferred_time=data.preferred_time,
    )

    event_id = create_event(
        name=client.name,
        contact=client.contact,
        service_name=service["name"],
        date=data.preferred_date,
        time=data.preferred_time,
        duration=service["duration"],
        preferred_contact_method=getattr(client, "preferred_contact_method", None),
        comment=data.comment,
        action_label="Новая запись",
    )

    booking = create_booking(
        client_id=client.id,
        data=data,
        duration=service["duration"],
        buffer_minutes=BUFFER_MINUTES,
        event_id=event_id,
        service=service,
        client=client,
    )

    try:
        append_booking_row([
            booking.id,
            booking.date,
            booking.time,
            booking.client_name or client.name,
            booking.client_contact or client.contact,
            booking.service_name or service["name"],
            booking.price or service.get("price"),
            booking.comment or "",
            booking.status,
            booking.client_status_snapshot or "",
            booking.preferred_contact_method or getattr(client, "preferred_contact_method", None) or "",
        ])
        logger.info("Booking appended to Google Sheets: %s", booking.id)
    except Exception:
        logger.exception("Failed to append booking to Google Sheets")

    create_lead(
        client_id=client.id,
        lead_type="booking_confirmed",
        status="booking_confirmed",
        comment=data.comment,
        service_id=data.service_id,
        preferred_date=data.preferred_date,
        preferred_time=data.preferred_time,
    )

    telegram_result = send_telegram_message(
        format_booking_created_message(
            client_name=client.name,
            contact=client.contact,
            service_name=service["name"],
            date=data.preferred_date,
            time=data.preferred_time,
            price=service.get("price"),
            preferred_contact_method=getattr(client, "preferred_contact_method", None),
            comment=data.comment,
        )
    )
    logger.info("Booking telegram result: %s", telegram_result)

    return {
        "status": "success",
        "message": build_booking_success_message(),
        "booking": {
            "booking_id": booking.id,
            "service": booking.service_name or service["name"],
            "service_id": booking.service_id,
            "price": booking.price,
            "date": booking.date,
            "time": booking.time,
            "duration_minutes": booking.duration_minutes,
            "buffer_minutes": booking.buffer_minutes,
            "client_name": booking.client_name or client.name,
            "contact": booking.client_contact or client.contact,
            "preferred_contact_method": booking.preferred_contact_method or getattr(client, "preferred_contact_method", None),
            "comment": booking.comment,
            "client_status_snapshot": booking.client_status_snapshot,
            "google_calendar_event_id": booking.google_calendar_event_id,
        },
        "lead_id": lead.id if lead else None,
    }


@app.post("/find-booking")
def api_find_booking(data: FindBookingRequest):
    bookings = get_client_active_bookings(
        name=data.name,
        contact=data.contact,
    )

    if not bookings:
        raise HTTPException(status_code=404, detail="Active bookings not found")

    result = []
    for booking in bookings:
        service = get_service(booking.service_id)

        result.append({
            "booking_id": booking.id,
            "service_id": booking.service_id,
            "service_name": booking.service_name or (service["name"] if service else booking.service_id),
            "price": booking.price,
            "date": booking.date,
            "time": booking.time,
            "status": booking.status,
            "comment": booking.comment,
            "contact": booking.client_contact,
            "client_name": booking.client_name,
            "preferred_contact_method": booking.preferred_contact_method,
            "google_calendar_event_id": booking.google_calendar_event_id,
            "client_status_snapshot": booking.client_status_snapshot,
        })

    return {
        "status": "success",
        "bookings": result,
        "count": len(result),
    }


@app.post("/cancel-booking")
def api_cancel_booking(data: CancelBookingRequest):
    booking = find_booking_by_id(data.booking_id)

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    client = get_client_by_id(booking.client_id)
    service = get_service(booking.service_id)

    updated = cancel_booking(
        booking_id=data.booking_id,
        reason=data.reason,
    )

    if not updated:
        raise HTTPException(status_code=400, detail="Unable to cancel booking")

    try:
        update_booking_status(updated.id, "cancelled")
        logger.info("Booking status updated in Google Sheets: %s", updated.id)
    except Exception:
        logger.exception("Failed to update booking status in Google Sheets")

    try:
        delete_event(booking.google_calendar_event_id)
    except Exception:
        logger.exception("Failed to delete Google Calendar event for booking_id=%s", booking.id)

    create_lead(
        client_id=updated.client_id,
        lead_type="cancellation",
        status="cancellation",
        service_id=updated.service_id,
        preferred_date=updated.date,
        preferred_time=updated.time,
        cancel_reason=data.reason,
    )

    telegram_result = send_telegram_message(
        format_booking_cancelled_message(
            client_name=client.name if client else (updated.client_name or "Неизвестный клиент"),
            contact=client.contact if client else (updated.client_contact or "—"),
            service_name=updated.service_name or (service["name"] if service else updated.service_id),
            date=updated.date,
            time=updated.time,
            preferred_contact_method=(
                getattr(client, "preferred_contact_method", None)
                if client
                else updated.preferred_contact_method
            ),
            cancel_reason=data.reason,
        )
    )
    logger.info("Cancel telegram result: %s", telegram_result)

    return {
        "status": "success",
        "message": "Запись отменена. Буду рад помочь с новой записью позже.",
        "booking_id": updated.id,
        "cancel_reason": data.reason,
    }


@app.post("/reschedule-booking")
def api_reschedule_booking(data: RescheduleBookingRequest):
    booking = find_booking_by_id(data.booking_id)

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    service = get_service(booking.service_id)

    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    ensure_slot_is_available(
        service_id=booking.service_id,
        date=data.new_date,
        slot_time=data.new_time,
    )

    client = get_client_by_id(booking.client_id)

    old_date = booking.date
    old_time = booking.time

    updated = reschedule_booking(
        booking_id=data.booking_id,
        new_date=data.new_date,
        new_time=data.new_time,
    )

    if not updated:
        raise HTTPException(status_code=400, detail="Unable to reschedule booking")

    try:
        update_booking_status(updated.id, "rescheduled")
        logger.info("Booking status updated in Google Sheets after reschedule: %s", updated.id)
    except Exception:
        logger.exception("Failed to update booking status in Google Sheets after reschedule")

    try:
        update_event(
            event_id=booking.google_calendar_event_id,
            date=data.new_date,
            time=data.new_time,
            duration=service["duration"],
            name=client.name if client else updated.client_name,
            contact=client.contact if client else updated.client_contact,
            service_name=updated.service_name or service["name"],
            preferred_contact_method=(
                getattr(client, "preferred_contact_method", None)
                if client
                else updated.preferred_contact_method
            ),
            comment=updated.comment,
            action_label="Перенос записи",
        )
    except Exception:
        logger.exception("Failed to update Google Calendar event for booking_id=%s", booking.id)

    create_lead(
        client_id=updated.client_id,
        lead_type="reschedule_request",
        status="reschedule_request",
        service_id=updated.service_id,
        preferred_date=updated.date,
        preferred_time=updated.time,
    )

    telegram_result = send_telegram_message(
        format_booking_rescheduled_message(
            client_name=client.name if client else (updated.client_name or "Неизвестный клиент"),
            contact=client.contact if client else (updated.client_contact or "—"),
            service_name=updated.service_name or service["name"],
            old_date=old_date,
            old_time=old_time,
            new_date=updated.date,
            new_time=updated.time,
            preferred_contact_method=(
                getattr(client, "preferred_contact_method", None)
                if client
                else updated.preferred_contact_method
            ),
            comment=updated.comment,
        )
    )
    logger.info("Reschedule telegram result: %s", telegram_result)

    return {
        "status": "success",
        "message": "Запись успешно перенесена.",
        "booking": {
            "booking_id": updated.id,
            "service_id": updated.service_id,
            "service_name": updated.service_name or service["name"],
            "price": updated.price,
            "date": updated.date,
            "time": updated.time,
            "status": updated.status,
            "comment": updated.comment,
            "contact": updated.client_contact or (client.contact if client else None),
            "client_name": updated.client_name or (client.name if client else None),
            "preferred_contact_method": updated.preferred_contact_method or (
                getattr(client, "preferred_contact_method", None) if client else None
            ),
            "client_status_snapshot": updated.client_status_snapshot,
            "google_calendar_event_id": updated.google_calendar_event_id,
        },
    }


@app.get("/debug/migrate-db")
def debug_migrate_db():
    if SessionLocal is None:
        raise HTTPException(status_code=500, detail="DATABASE_URL is not configured")

    sql_commands = [
        "ALTER TABLE clients ADD COLUMN IF NOT EXISTS client_status VARCHAR(50) NOT NULL DEFAULT 'new';",
        "ALTER TABLE clients ADD COLUMN IF NOT EXISTS visits_count INTEGER NOT NULL DEFAULT 0;",
        "ALTER TABLE clients ADD COLUMN IF NOT EXISTS is_blacklisted BOOLEAN NOT NULL DEFAULT FALSE;",
        "ALTER TABLE clients ADD COLUMN IF NOT EXISTS blacklist_reason TEXT;",

        "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS service_name VARCHAR(255);",
        "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS price INTEGER;",
        "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS client_name VARCHAR(255);",
        "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS client_contact VARCHAR(255);",
        "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS preferred_contact_method VARCHAR(50);",
        "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS client_status_snapshot VARCHAR(50);",
    ]

    db = SessionLocal()
    try:
        for command in sql_commands:
            db.execute(text(command))
        db.commit()

        return {
            "status": "success",
            "message": "Database migration completed",
        }
    except Exception as e:
        db.rollback()
        logger.exception("Database migration failed")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
