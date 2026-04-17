from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.services import SERVICES, FAQ, get_service
from app.calendar import generate_slots, create_event, delete_event, update_event
from app.config import BUFFER_MINUTES
from app.db import Base, engine
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
    find_booking,
    cancel_booking,
    reschedule_booking,
    find_booking_by_id,
)
from app.telegram import send_telegram_message

app = FastAPI(title="Nail Master Booking Bot")

if engine is not None:
    Base.metadata.create_all(bind=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    client = get_or_create_client(
        name=data.name,
        contact=data.contact,
    )

    lead = create_lead(
        client_id=client.id,
        lead_type="contact_request",
        status="contact_request",
        comment=data.comment,
    )

    send_telegram_message(
        f"Новая заявка на связь:\n"
        f"Имя: {data.name}\n"
        f"Контакт: {data.contact}\n"
        f"Способ связи: {data.preferred_contact_method}\n"
        f"Комментарий: {data.comment or '—'}"
    )

    return {
        "status": "success",
        "message": "Спасибо! Александр свяжется с вами в течение суток удобным для вас способом.",
        "client_id": client.id,
        "lead_id": lead.id if lead else None,
    }


@app.post("/booking-lead")
def create_booking_lead(data: BookingLeadCreate):
    service = get_service(data.service_id)

    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    client = get_or_create_client(
        name=data.name,
        contact=data.contact,
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
        data.name,
        service["name"],
        data.preferred_date,
        data.preferred_time,
        service["duration"],
    )

    booking = create_booking(
        client_id=client.id,
        data=data,
        duration=service["duration"],
        buffer_minutes=BUFFER_MINUTES,
        event_id=event_id,
    )

    create_lead(
        client_id=client.id,
        lead_type="booking_confirmed",
        status="booking_confirmed",
        comment=data.comment,
        service_id=data.service_id,
        preferred_date=data.preferred_date,
        preferred_time=data.preferred_time,
    )

    send_telegram_message(
        f"Новая запись:\n"
        f"Имя: {data.name}\n"
        f"Контакт: {data.contact}\n"
        f"Услуга: {service['name']}\n"
        f"Дата: {data.preferred_date}\n"
        f"Время: {data.preferred_time}\n"
        f"Комментарий: {data.comment or '—'}"
    )

    return {
        "status": "success",
        "message": build_booking_success_message(),
        "booking": {
            "booking_id": booking.id,
            "service": service["name"],
            "date": booking.date,
            "time": booking.time,
            "duration_minutes": booking.duration_minutes,
            "buffer_minutes": booking.buffer_minutes,
            "client_name": client.name,
            "contact": client.contact,
            "comment": booking.comment,
            "google_calendar_event_id": booking.google_calendar_event_id,
        },
        "lead_id": lead.id if lead else None,
    }


@app.post("/find-booking")
def api_find_booking(data: FindBookingRequest):
    booking = find_booking(
        name=data.name,
        contact=data.contact,
    )

    if not booking:
        raise HTTPException(status_code=404, detail="Active booking not found")

    service = get_service(booking.service_id)

    return {
        "status": "success",
        "booking": {
            "booking_id": booking.id,
            "service_id": booking.service_id,
            "service_name": service["name"] if service else booking.service_id,
            "date": booking.date,
            "time": booking.time,
            "status": booking.status,
            "comment": booking.comment,
            "google_calendar_event_id": booking.google_calendar_event_id,
        },
    }


@app.post("/cancel-booking")
def api_cancel_booking(data: CancelBookingRequest):
    booking = find_booking_by_id(data.booking_id)

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    updated = cancel_booking(
        booking_id=data.booking_id,
        reason=data.reason,
    )

    if not updated:
        raise HTTPException(status_code=400, detail="Unable to cancel booking")

    delete_event(booking.google_calendar_event_id)

    create_lead(
        client_id=updated.client_id,
        lead_type="cancellation",
        status="cancellation",
        service_id=updated.service_id,
        preferred_date=updated.date,
        preferred_time=updated.time,
        cancel_reason=data.reason,
    )

    send_telegram_message(
        f"Отмена записи:\n"
        f"Booking ID: {updated.id}\n"
        f"Услуга: {updated.service_id}\n"
        f"Дата: {updated.date}\n"
        f"Время: {updated.time}\n"
        f"Причина: {data.reason or 'не указана'}"
    )

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

    updated = reschedule_booking(
        booking_id=data.booking_id,
        new_date=data.new_date,
        new_time=data.new_time,
    )

    if not updated:
        raise HTTPException(status_code=400, detail="Unable to reschedule booking")

    service = get_service(updated.service_id)

    update_event(
        booking.google_calendar_event_id,
        data.new_date,
        data.new_time,
        service["duration"],
    )

    create_lead(
        client_id=updated.client_id,
        lead_type="reschedule_request",
        status="reschedule_request",
        service_id=updated.service_id,
        preferred_date=updated.date,
        preferred_time=updated.time,
    )

    send_telegram_message(
        f"Перенос записи:\n"
        f"Booking ID: {updated.id}\n"
        f"Услуга: {service['name'] if service else updated.service_id}\n"
        f"Новая дата: {updated.date}\n"
        f"Новое время: {updated.time}"
    )

    return {
        "status": "success",
        "message": "Запись успешно перенесена.",
        "booking": {
            "booking_id": updated.id,
            "service_id": updated.service_id,
            "service_name": service["name"] if service else updated.service_id,
            "date": updated.date,
            "time": updated.time,
            "status": updated.status,
            "google_calendar_event_id": updated.google_calendar_event_id,
        },
    }
