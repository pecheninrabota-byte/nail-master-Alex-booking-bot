from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.services import SERVICES, FAQ, get_service
from app.calendar import generate_slots, create_event_mock
from app.models import BookingRequest

app = FastAPI(title="Nail Master Booking Bot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"status": "ok", "message": "Nail Master Booking API is running"}


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
    return {"service_id": service_id, "date": date, "slots": slots}


@app.post("/book")
def book(data: BookingRequest):
    service = get_service(data.service_id)

    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    result = create_event_mock(data.model_dump(), service)
    return result
