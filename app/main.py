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
    create_client,
    create_lead,
    create_booking,
    find_active_booking_by_name_and_contact,
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


# ===== ROOT =====
@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "Nail Master Booking API is running",
    }


# ===== SERVICES =====
@app.get("/services")
def get_services():
    return SERVICES


@app.get("/faq")
def get_faq():
    return FAQ


# ===== SLOTS =====
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


# ===== SERVICE RECOMMENDATION =====
@app.post("/service-recommendation", response_model=ServiceRecommendationResponse)
def service_recommendation(data: ServiceRecommendationRequest):
    recommended_services, explanation = recommend_services(
        category=data.category,
        care_needed=data.care_needed,
        coating_type=data.coating_type,
    )

    return {
        "recommended_services": recommended_services,
        "explanation": explanation,
    }


# ===== CONTACT REQUEST =====
@app.post("/contact-request")
def create_contact_request(data: ContactRequestCreate):
    client = create_client(
        name=data.name,
        contact=data.contact,
        preferred_contact_method=data.preferred_contact_method,
    )

    lead = create_lead(
        client_id=client["id"],
        lead_type="contact_request",
        status="contact_request",
        comment=data.comment,
    )

    send_telegram_message(
        f"Новая заявка на связь:\n{data.name}\n{data.contact}"
    )

    return {
        "status": "success",
        "message": "Спасибо! Александр свяжется с вами в течение суток удобным для вас способом.",
        "client_id": client["id"],
        "lead_id": lead["id"],
    }


# ===== BOOKING =====
@app.post("/booking-lead")
def create_booking_lead(data: BookingLeadCreate):
    service = get_service(data.service_id)

    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    client = create_client(
        name=data.name,
        contact=data.contact,
        preferred_contact_method=None,
    )

    # лид: начало записи
    lead = create_lead(
        client_id=client["id"],
        lead_type="booking_started",
        status="booking_started",
        comment=data.comment,
        service_id=data.service_id,
        preferred_date=data.preferred_date,
        preferred_time=data.preferred_time,
    )

    # 🔥 создаём событие в календаре
    event_id = create_event(
        data.name,
        service["name"],
        data.preferred_date,
        data.preferred_time,
        service["duration"],
    )

    # создаём booking
    booking = create_booking(
        client_id=client["id"],
        service_id=data.service_id,
        date=data.preferred_date,
        time=data.preferred_time,
        duration_minutes=service["duration"],
        buffer_minutes=BUFFER_MINUTES,
        comment=data.comment,
        google_calendar_event_id=event_id,
    )

    # лид: подтверждение
    create_lead(
        client_id=client["id"],
        lead_type="booking_confirmed",
        status="booking_confirmed",
        comment=data.comment,
        service_id=data.service_id,
        preferred_date=data.preferred_date,
        preferred_time=data.preferred_time,
    )

    # Telegram
    send_telegram_message(
        f"Новая запись:\n"
        f"{data.name}\n"
        f"{data.contact}\n"
        f"{service['name']}\n"
        f"{data.preferred_date} {data.preferred_time}"
    )

    return {
        "status": "success",
        "message": build_booking_success_message(),
        "booking": {
            "booking_id": booking["id"],
            "service": service["name"],
            "date": booking["date"],
            "time": booking["time"],
            "duration_minutes": booking["duration_minutes"],
            "buffer_minutes": booking["buffer_minutes"],
            "client_name": client["name"],
            "contact": client["contact"],
            "comment": booking["comment"],
        },
        "lead_id": lead["id"],
    }


# ===== FIND BOOKING =====
@app.post("/find-booking")
def find_booking(data: FindBookingRequest):
    booking = find_active_booking_by_name_and_contact(
        name=data.name,
        contact=data.contact,
    )

    if not booking:
        raise HTTPException(status_code=404, detail="Active booking not found")

    service = get_service(booking["service_id"])

    return {
        "status": "success",
        "booking": {
            "booking_id": booking["id"],
            "service_id": booking["service_id"],
            "service_name": service["name"] if service else booking["service_id"],
            "date": booking["date"],
            "time": booking["time"],
            "status": booking["status"],
            "comment": booking.get("comment"),
        },
    }


# ===== CANCEL =====
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

    # 🔥 удаляем из календаря
    delete_event(booking.get("google_calendar_event_id"))

    create_lead(
        client_id=updated["client_id"],
        lead_type="cancellation",
        status="cancellation",
        service_id=updated["service_id"],
        preferred_date=updated["date"],
        preferred_time=updated["time"],
        cancel_reason=data.reason,
    )

    send_telegram_message(f"Отмена записи: {data.booking_id}")

    return {
        "status": "success",
        "message": "Запись отменена. Буду рад помочь с новой записью позже.",
        "booking_id": updated["id"],
        "cancel_reason": data.reason,
    }


# ===== RESCHEDULE =====
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

    service = get_service(updated["service_id"])

    # 🔥 обновляем в календаре
    update_event(
        booking.get("google_calendar_event_id"),
        data.new_date,
        data.new_time,
        service["duration"],
    )

    create_lead(
        client_id=updated["client_id"],
        lead_type="reschedule_request",
        status="reschedule_request",
        service_id=updated["service_id"],
        preferred_date=updated["date"],
        preferred_time=updated["time"],
    )

    send_telegram_message(f"Перенос записи: {data.booking_id}")

    return {
        "status": "success",
        "message": "Запись успешно перенесена.",
        "booking": {
            "booking_id": updated["id"],
            "service_id": updated["service_id"],
            "service_name": service["name"] if service else updated["service_id"],
            "date": updated["date"],
            "time": updated["time"],
            "status": updated["status"],
        },
    }
