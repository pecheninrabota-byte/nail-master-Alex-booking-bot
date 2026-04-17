from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.services import SERVICES, FAQ, get_service
from app.calendar import generate_slots
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

app = FastAPI(title="Nail Master Booking Bot")
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

    # Пока календарь ещё не интегрирован, generate_slots просто отдаёт доступные интервалы
    # по рабочему дню. Но уже учитываем буфер в 30 минут через duration.
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

    # Пока клиента нет, lead фиксируем позже, когда появятся имя и контакт.
    return {
        "recommended_services": recommended_services,
        "explanation": explanation,
    }


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

    return {
        "status": "success",
        "message": "Спасибо! Александр свяжется с вами в течение суток удобным для вас способом.",
        "client_id": client["id"],
        "lead_id": lead["id"],
    }


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

    lead = create_lead(
        client_id=client["id"],
        lead_type="booking_started",
        status="booking_started",
        comment=data.comment,
        service_id=data.service_id,
        preferred_date=data.preferred_date,
        preferred_time=data.preferred_time,
    )

    booking = create_booking(
        client_id=client["id"],
        service_id=data.service_id,
        date=data.preferred_date,
        time=data.preferred_time,
        duration_minutes=service["duration"],
        buffer_minutes=BUFFER_MINUTES,
        comment=data.comment,
    )

    create_lead(
        client_id=client["id"],
        lead_type="booking_confirmed",
        status="booking_confirmed",
        comment=data.comment,
        service_id=data.service_id,
        preferred_date=data.preferred_date,
        preferred_time=data.preferred_time,
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

    create_lead(
        client_id=updated["client_id"],
        lead_type="cancellation",
        status="cancellation",
        service_id=updated["service_id"],
        preferred_date=updated["date"],
        preferred_time=updated["time"],
        cancel_reason=data.reason,
    )

    return {
        "status": "success",
        "message": "Запись отменена. Буду рад помочь с новой записью позже.",
        "booking_id": updated["id"],
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

    create_lead(
        client_id=updated["client_id"],
        lead_type="reschedule_request",
        status="reschedule_request",
        service_id=updated["service_id"],
        preferred_date=updated["date"],
        preferred_time=updated["time"],
    )

    service = get_service(updated["service_id"])

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
