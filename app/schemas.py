from typing import Optional, Literal
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
    category: CategoryType = Field(..., description="Что интересует: manicure / pedicure / combo")
    care_needed: YesNoType = Field(..., description="Нужен ли дополнительный уход: yes / no")
    coating_type: CoatingType = Field(..., description="Тип покрытия: none / lacquer / gel / films")


class ServiceRecommendationResponse(BaseModel):
    recommended_services: list[dict]
    explanation: str
    recommended_ids: list[str]


class ContactRequestCreate(BaseModel):
    name: str = Field(..., description="Имя и фамилия или псевдоним")
    contact: str = Field(..., description="Телефон или Telegram username")
    preferred_contact_method: ContactMethodType = Field(..., description="telegram / phone")
    comment: Optional[str] = Field(default=None, description="Комментарий")


class BookingLeadCreate(BaseModel):
    name: str = Field(..., description="Имя и фамилия или псевдоним")
    contact: str = Field(..., description="Телефон или Telegram username")
    preferred_contact_method: Optional[ContactMethodType] = Field(default=None, description="telegram / phone")
    service_id: str = Field(..., description="ID услуги")
    preferred_date: str = Field(..., description="Дата YYYY-MM-DD")
    preferred_time: str = Field(..., description="Время HH:MM")
    comment: Optional[str] = Field(default=None, description="Комментарий")


class FindBookingRequest(BaseModel):
    name: str = Field(..., description="Имя")
    contact: str = Field(..., description="Контакт")


class CancelBookingRequest(BaseModel):
    booking_id: str = Field(..., description="ID записи")
    reason: Optional[str] = Field(default=None, description="Причина отмены")


class RescheduleBookingRequest(BaseModel):
    booking_id: str = Field(..., description="ID записи")
    new_date: str = Field(..., description="Новая дата YYYY-MM-DD")
    new_time: str = Field(..., description="Новое время HH:MM")
