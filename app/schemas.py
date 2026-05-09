from typing import Literal, Optional

from pydantic import BaseModel, Field


CategoryType = Literal["manicure", "pedicure", "combo"]
YesNoType = Literal["yes", "no"]
CoatingType = Literal["none", "lacquer", "gel", "films"]
ContactMethodType = Literal["telegram", "phone"]

LeadStatusType = Literal[
    "booking_started",
    "booking_confirmed",
    "service_selection_help",
    "contact_request",
    "reschedule_request",
    "cancellation",
]

BookingStatusType = Literal["confirmed", "cancelled", "rescheduled"]
ClientStatusType = Literal["new", "returned", "regular", "left", "claim", "blacklist"]


class ServiceRecommendationRequest(BaseModel):
    category: CategoryType
    care_needed: YesNoType
    coating_type: CoatingType


class ServiceRecommendationResponse(BaseModel):
    recommended_services: list[dict]
    explanation: str
    recommended_ids: list[str]


class ContactRequestCreate(BaseModel):
    name: str
    contact: str
    preferred_contact_method: ContactMethodType
    comment: Optional[str] = None


class BookingLeadCreate(BaseModel):
    name: str
    contact: str
    preferred_contact_method: Optional[ContactMethodType] = None

    service_id: Optional[str] = None
    service_ids: Optional[list[str]] = None

    preferred_date: str
    preferred_time: str
    comment: Optional[str] = None


class FindBookingRequest(BaseModel):
    name: str
    contact: str


class CancelBookingRequest(BaseModel):
    booking_id: str
    reason: Optional[str] = None


class RescheduleBookingRequest(BaseModel):
    booking_id: str
    new_date: str
    new_time: str
