from __future__ import annotations

from datetime import datetime

from app.services import get_service


def get_greeting_by_time() -> str:
    hour = datetime.now().hour

    if 6 <= hour < 18:
        return "Желаю вам хорошего дня."
    if 18 <= hour < 23:
        return "Желаю вам хорошего вечера."
    return "Желаю вам доброй ночи."


def build_booking_success_message() -> str:
    return (
        "Вы успешно записаны. "
        "Александр свяжется с вами за день до вашей записи для подтверждения. "
        f"{get_greeting_by_time()}"
    )


def recommend_services(category: str, care_needed: str, coating_type: str) -> tuple[list[dict], str]:
    recommendations: list[dict] = []

    manicure_map = {
        "none": "file_manicure_spa" if care_needed == "yes" else "file_manicure",
        "lacquer": "file_manicure_lacquer",
        "gel": "file_manicure_gel",
        "films": "file_manicure_films",
    }

    pedicure_map = {
        "none": "file_pedicure_spa" if care_needed == "yes" else "file_pedicure",
        "lacquer": "file_pedicure_lacquer",
        "gel": None,   # в текущем прайсе нет отдельной карточки "педикюр + гель-лак"
        "films": "file_pedicure_films",
    }

    if category == "manicure":
        service_id = manicure_map.get(coating_type)
        if service_id:
            service = get_service(service_id)
            if service:
                recommendations.append(service)

    elif category == "pedicure":
        service_id = pedicure_map.get(coating_type)
        if service_id:
            service = get_service(service_id)
            if service:
                recommendations.append(service)

    elif category == "combo":
        manicure_id = manicure_map.get(coating_type)
        pedicure_id = pedicure_map.get(coating_type)

        if manicure_id:
            manicure_service = get_service(manicure_id)
            if manicure_service:
                recommendations.append(manicure_service)

        if pedicure_id:
            pedicure_service = get_service(pedicure_id)
            if pedicure_service:
                recommendations.append(pedicure_service)

    if not recommendations:
        explanation = (
            "Я не нашёл идеального совпадения по текущему прайсу. "
            "Лучше оставить заявку, и Александр поможет подобрать оптимальный вариант."
        )
        return [], explanation

    explanation = build_recommendation_explanation(category, care_needed, coating_type, recommendations)
    return recommendations, explanation


def build_recommendation_explanation(
    category: str,
    care_needed: str,
    coating_type: str,
    recommendations: list[dict],
) -> str:
    category_map = {
        "manicure": "маникюр",
        "pedicure": "педикюр",
        "combo": "комплекс маникюр + педикюр",
    }

    coating_map = {
        "none": "без покрытия",
        "lacquer": "с обычным лаком",
        "gel": "с гель-лаком",
        "films": "с плёночным покрытием",
    }

    care_text = "с дополнительным уходом" if care_needed == "yes" else "без дополнительного ухода"

    names = ", ".join(service["name"] for service in recommendations)

    return (
        f"На основе ваших ответов вам подойдёт {category_map.get(category, 'услуга')} "
        f"{coating_map.get(coating_type, '')} {care_text}. "
        f"Рекомендую: {names}."
    ).replace("  ", " ").strip()


def get_total_duration_with_buffer(service: dict, buffer_minutes: int) -> int:
    return service["duration"] + buffer_minutes
