import logging
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import BUFFER_MINUTES
from app.db import Base, engine
from app.schemas import (
    BookingLeadCreate,
    CancelBookingRequest,
    ContactRequestCreate,
    FindBookingRequest,
    RescheduleBookingRequest,
    ServiceRecommendationRequest,
)
from app.services import SERVICES, build_combined_service, get_service
from app.storage import (
    cancel_booking,
    create_booking,
    create_lead,
    find_booking_by_id,
    get_client_active_bookings,
    get_or_create_client,
    is_client_blacklisted,
    remove_client_blacklist,
    reschedule_booking,
    set_client_blacklist,
)
from app.calendar import generate_slots, create_event, delete_event, update_event
from app.sheets import (
    append_booking_row,
    update_booking_status,
    update_booking_row_after_reschedule,
    is_contact_blacklisted_in_sheet,
    is_booking_active_by_sheet,
)

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="Alex Booking Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


FAQ = [
    {
        "question": "Сколько держится покрытие?",
        "answer": "Обычно покрытие держится 2–4 недели. Точный срок зависит от состояния ногтей и ухода после процедуры.",
    },
    {
        "question": "Можно ли записаться на несколько услуг сразу?",
        "answer": "Да, можно выбрать несколько услуг. Система посчитает общую длительность и стоимость.",
    },
    {
        "question": "Как отменить или перенести запись?",
        "answer": "Через бот на сайте: выберите перенос или отмену записи и укажите контакт, который использовали при записи.",
    },
]


def normalize_service_ids(data: BookingLeadCreate) -> list[str]:
    if data.service_ids and len(data.service_ids) > 0:
        return data.service_ids

    if data.service_id:
        return [data.service_id]

    raise HTTPException(status_code=400, detail="service_id or service_ids is required")


def normalize_service_ids_from_query(
    service_id: str | None = None,
    service_ids: str | None = None,
) -> list[str]:
    if service_ids:
        ids = [item.strip() for item in service_ids.split(",") if item.strip()]
        if ids:
            return ids

    if service_id:
        return [service_id]

    raise HTTPException(status_code=400, detail="service_id or service_ids is required")


def build_booking_service(service_ids: list[str]) -> dict:
    try:
        return build_combined_service(service_ids)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


def booking_to_dict(booking):
    return {
        "booking_id": booking.id,
        "service_id": booking.service_id,
        "service_ids": booking.service_id.split("+") if booking.service_id else [],
        "service_name": booking.service_name,
        "price": booking.price,
        "date": booking.date,
        "time": booking.time,
        "duration_minutes": booking.duration_minutes,
        "buffer_minutes": booking.buffer_minutes,
        "status": booking.status,
        "comment": booking.comment,
        "client_name": booking.client_name,
        "contact": booking.client_contact,
        "preferred_contact_method": booking.preferred_contact_method,
        "client_status_snapshot": booking.client_status_snapshot,
        "google_calendar_event_id": booking.google_calendar_event_id,
    }


def safe_sheets_append(row: list):
    try:
        append_booking_row(row)
    except Exception as e:
        logger.exception("Google Sheets append failed: %s", e)


def safe_sheets_status(booking_id: str, status: str):
    try:
        update_booking_status(booking_id, status)
    except Exception as e:
        logger.exception("Google Sheets status update failed: %s", e)


def safe_sheets_reschedule(booking_id: str, new_date: str, new_time: str):
    try:
        update_booking_row_after_reschedule(booking_id, new_date, new_time, "rescheduled")
    except Exception as e:
        logger.exception("Google Sheets reschedule update failed: %s", e)


def safe_sheet_blacklist_check(contact: str) -> bool:
    try:
        return is_contact_blacklisted_in_sheet(contact)
    except Exception as e:
        logger.exception("Google Sheets blacklist check failed: %s", e)
        return False


def safe_sheet_booking_active_check(booking_id: str) -> bool:
    try:
        return is_booking_active_by_sheet(booking_id)
    except Exception as e:
        logger.exception("Google Sheets booking active check failed: %s", e)
        return True


def send_telegram_safely(message: str):
    try:
        from app.telegram import send_telegram_message

        send_telegram_message(message)
    except Exception as e:
        logger.exception("Telegram send failed: %s", e)


@app.get("/")
def root():
    return {"status": "ok", "message": "Alex Booking Backend is running"}


@app.get("/services")
def get_services():
    return {"services": SERVICES}


@app.get("/faq")
def get_faq():
    return {"faq": FAQ}


@app.get("/slots")
def get_slots(
    service_id: str | None = Query(default=None),
    service_ids: str | None = Query(default=None),
    date: str = Query(...),
):
    ids = normalize_service_ids_from_query(service_id=service_id, service_ids=service_ids)
    service = build_booking_service(ids)

    slots = generate_slots(date, service["duration"])

    return {
        "status": "success",
        "service": service,
        "service_id": service["id"],
        "service_ids": service["ids"],
        "date": date,
        "duration_minutes": service["duration"],
        "buffer_minutes": BUFFER_MINUTES,
        "slots": slots,
    }


@app.post("/service-recommendation")
def service_recommendation(data: ServiceRecommendationRequest):
    recommended = []

    if data.category == "combo":
        recommended = [
            get_service("combo_file_manicure_pedicure_films"),
        ]
    elif data.category == "manicure":
        if data.coating_type == "films":
            recommended = [get_service("file_manicure_films")]
        elif data.coating_type == "gel":
            recommended = [get_service("file_manicure_gel_lacquer")]
        elif data.coating_type == "lacquer":
            recommended = [get_service("file_manicure_lacquer")]
        else:
            recommended = [get_service("file_manicure")]
    elif data.category == "pedicure":
        if data.coating_type == "films":
            recommended = [get_service("file_pedicure_films")]
        elif data.coating_type == "lacquer":
            recommended = [get_service("file_pedicure_lacquer")]
        else:
            recommended = [get_service("file_pedicure")]

    recommended = [item for item in recommended if item]

    return {
        "recommended_services": recommended,
        "recommended_ids": [item["id"] for item in recommended],
        "explanation": "Подобрал услуги по вашим ответам. Можно выбрать одну или несколько услуг для записи.",
    }


@app.post("/contact-request")
def contact_request(data: ContactRequestCreate):
    client = get_or_create_client(
        name=data.name,
        contact=data.contact,
        preferred_contact_method=data.preferred_contact_method,
    )

    create_lead(
        client_id=client.id,
        lead_type="contact_request",
        status="contact_request",
        comment=data.comment,
    )

    message = (
        "💬 Новая заявка на связь\n\n"
        f"Имя: {data.name}\n"
        f"Контакт: {data.contact}\n"
        f"Способ связи: {data.preferred_contact_method}\n"
        f"Комментарий: {data.comment or '—'}"
    )
    send_telegram_safely(message)

    return {"status": "success", "message": "Contact request created"}


@app.post("/booking-lead")
def booking_lead(data: BookingLeadCreate):
    sheet_blacklisted = safe_sheet_blacklist_check(data.contact)

    if sheet_blacklisted:
        try:
            set_client_blacklist(
                contact=data.contact,
                reason="Marked as blacklist in Google Sheets",
            )
        except Exception as e:
            logger.exception("Failed to sync blacklist from Google Sheets to Postgres: %s", e)

    if is_client_blacklisted(data.contact) or sheet_blacklisted:
        raise HTTPException(
            status_code=403,
            detail="Booking is not available for this client. Please contact the master directly.",
        )

    service_ids = normalize_service_ids(data)
    service = build_booking_service(service_ids)

    slots = generate_slots(data.preferred_date, service["duration"])
    if data.preferred_time not in slots:
        raise HTTPException(
            status_code=400,
            detail="Selected time slot is not available",
        )

    client = get_or_create_client(
        name=data.name,
        contact=data.contact,
        preferred_contact_method=data.preferred_contact_method,
    )

    create_lead(
        client_id=client.id,
        lead_type="booking_started",
        status="booking_started",
        service_id=service["id"],
        preferred_date=data.preferred_date,
        preferred_time=data.preferred_time,
        comment=data.comment,
    )

    event_id = create_event(
        name=data.name,
        contact=data.contact,
        service_name=service["name"],
        date=data.preferred_date,
        time=data.preferred_time,
        duration=service["duration"],
        preferred_contact_method=data.preferred_contact_method,
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

    create_lead(
        client_id=client.id,
        lead_type="booking_confirmed",
        status="booking_confirmed",
        service_id=service["id"],
        preferred_date=data.preferred_date,
        preferred_time=data.preferred_time,
        comment=data.comment,
    )

    safe_sheets_append(
        [
            booking.id,
            booking.date,
            booking.time,
            booking.client_name,
            booking.client_contact,
            booking.service_name,
            booking.price,
            booking.comment or "",
            "waiting_confirmation",
            booking.client_status_snapshot or "",
            booking.preferred_contact_method or "",
        ]
    )

    message = (
        "🟢 Новая запись\n\n"
        f"ID: {booking.id}\n"
        f"Имя: {booking.client_name}\n"
        f"Контакт: {booking.client_contact}\n"
        f"Способ связи: {booking.preferred_contact_method or '—'}\n"
        f"Услуга: {booking.service_name}\n"
        f"Стоимость: {booking.price} ₽\n"
        f"Дата: {booking.date}\n"
        f"Время: {booking.time}\n"
        f"Длительность: {booking.duration_minutes} мин\n"
        f"Статус записи: Ожидает подтверждения\n"
        f"Комментарий: {booking.comment or '—'}"
    )
    send_telegram_safely(message)

    return {
        "status": "success",
        "booking": booking_to_dict(booking),
    }


@app.post("/find-booking")
def find_booking(data: FindBookingRequest):
    bookings = get_client_active_bookings(data.name, data.contact)

    bookings = [
        booking for booking in bookings
        if safe_sheet_booking_active_check(booking.id)
    ]

    return {
        "status": "success",
        "bookings": [booking_to_dict(item) for item in bookings],
        "count": len(bookings),
    }


@app.post("/cancel-booking")
def cancel_booking_endpoint(data: CancelBookingRequest):
    booking = find_booking_by_id(data.booking_id)

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if not safe_sheet_booking_active_check(booking.id):
        raise HTTPException(
            status_code=400,
            detail="This booking is already closed in CRM",
        )

    updated = cancel_booking(data.booking_id, data.reason)

    if booking.google_calendar_event_id:
        try:
            delete_event(booking.google_calendar_event_id)
        except Exception as e:
            logger.exception("Google Calendar delete failed: %s", e)

    safe_sheets_status(data.booking_id, "cancelled")

    create_lead(
        client_id=updated.client_id,
        lead_type="cancellation",
        status="cancellation",
        service_id=updated.service_id,
        preferred_date=updated.date,
        preferred_time=updated.time,
        comment=updated.comment,
        cancel_reason=data.reason,
    )

    message = (
        "🔴 Отмена записи\n\n"
        f"ID: {updated.id}\n"
        f"Имя: {updated.client_name}\n"
        f"Контакт: {updated.client_contact}\n"
        f"Услуга: {updated.service_name}\n"
        f"Дата: {updated.date}\n"
        f"Время: {updated.time}\n"
        f"Причина: {data.reason or '—'}"
    )
    send_telegram_safely(message)

    return {
        "status": "success",
        "booking": booking_to_dict(updated),
    }


@app.post("/reschedule-booking")
def reschedule_booking_endpoint(data: RescheduleBookingRequest):
    booking = find_booking_by_id(data.booking_id)

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if not safe_sheet_booking_active_check(booking.id):
        raise HTTPException(
            status_code=400,
            detail="This booking is already closed in CRM",
        )

    slots = generate_slots(data.new_date, booking.duration_minutes)
    if data.new_time not in slots:
        raise HTTPException(
            status_code=400,
            detail="Selected time slot is not available",
        )

    if booking.google_calendar_event_id:
        try:
            update_event(
                event_id=booking.google_calendar_event_id,
                date=data.new_date,
                time=data.new_time,
                duration=booking.duration_minutes,
                name=booking.client_name,
                contact=booking.client_contact,
                service_name=booking.service_name,
                preferred_contact_method=booking.preferred_contact_method,
                comment=booking.comment,
                action_label="Перенос записи",
            )
        except Exception as e:
            logger.exception("Google Calendar update failed: %s", e)

    updated = reschedule_booking(data.booking_id, data.new_date, data.new_time)

    safe_sheets_reschedule(data.booking_id, data.new_date, data.new_time)

    create_lead(
        client_id=updated.client_id,
        lead_type="reschedule_request",
        status="reschedule_request",
        service_id=updated.service_id,
        preferred_date=updated.date,
        preferred_time=updated.time,
        comment=updated.comment,
    )

    message = (
        "🟡 Перенос записи\n\n"
        f"ID: {updated.id}\n"
        f"Имя: {updated.client_name}\n"
        f"Контакт: {updated.client_contact}\n"
        f"Услуга: {updated.service_name}\n"
        f"Новая дата: {updated.date}\n"
        f"Новое время: {updated.time}\n"
        f"Длительность: {updated.duration_minutes} мин"
    )
    send_telegram_safely(message)

    return {
        "status": "success",
        "booking": booking_to_dict(updated),
    }


@app.get("/debug/migrate-db")
def debug_migrate_db():
    if engine is None:
        raise HTTPException(status_code=500, detail="DATABASE_URL is missing")

    Base.metadata.create_all(bind=engine)

    statements = [
        "ALTER TABLE clients ADD COLUMN IF NOT EXISTS client_status VARCHAR DEFAULT 'new' NOT NULL",
        "ALTER TABLE clients ADD COLUMN IF NOT EXISTS visits_count INTEGER DEFAULT 0 NOT NULL",
        "ALTER TABLE clients ADD COLUMN IF NOT EXISTS is_blacklisted BOOLEAN DEFAULT FALSE NOT NULL",
        "ALTER TABLE clients ADD COLUMN IF NOT EXISTS blacklist_reason TEXT",
        "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS service_name VARCHAR",
        "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS price INTEGER",
        "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS client_name VARCHAR",
        "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS client_contact VARCHAR",
        "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS preferred_contact_method VARCHAR",
        "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS client_status_snapshot VARCHAR",
    ]

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))

    return {
        "status": "success",
        "message": "Database migration completed",
    }


@app.get("/debug/sheets")
def debug_sheets():
    test_id = f"debug-{datetime.utcnow().isoformat()}"

    append_booking_row(
        [
            test_id,
            "2026-01-01",
            "10:00",
            "Тестовый клиент",
            "@test",
            "Тестовая услуга",
            1000,
            "Тестовая строка из /debug/sheets",
            "debug",
            "new",
            "telegram",
        ]
    )

    return {
        "status": "success",
        "message": "Test row added to Google Sheets",
        "booking_id": test_id,
    }


@app.post("/debug/blacklist/add")
def debug_blacklist_add(contact: str, reason: str | None = None):
    client = set_client_blacklist(contact=contact, reason=reason)

    return {
        "status": "success",
        "client_id": client.id,
        "contact": client.contact,
        "is_blacklisted": client.is_blacklisted,
        "reason": client.blacklist_reason,
    }


@app.post("/debug/blacklist/remove")
def debug_blacklist_remove(contact: str):
    client = remove_client_blacklist(contact=contact)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    return {
        "status": "success",
        "client_id": client.id,
        "contact": client.contact,
        "is_blacklisted": client.is_blacklisted,
    }
