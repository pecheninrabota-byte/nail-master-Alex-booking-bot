from pydantic import BaseModel, Field


class BookingRequest(BaseModel):
    service_id: str = Field(..., description="ID услуги")
    date: str = Field(..., description="Дата в формате DD-MM-YYYY")
    time: str = Field(..., description="Время в формате HH:MM")
    name: str = Field(..., description="Имя клиента")
    contact: str = Field(..., description="Телефон, Telegram или другой контакт")
    comment: str | None = Field(default=None, description="Комментарий клиента")
