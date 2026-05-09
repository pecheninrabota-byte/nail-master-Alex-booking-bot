SERVICES = [
    {
        "id": "combo_file_manicure_pedicure_spa",
        "name": "Маникюр пилочный + педикюр пилочный + SPA",
        "category": "combo",
        "price": 6000,
        "duration": 120,
        "desc": "Бережный уход и восстановление кожи",
        "bullets": ["обработка без травм", "глубокое увлажнение кожи", "восстановление и питание"],
    },
    {
        "id": "combo_file_manicure_pedicure_films",
        "name": "Маникюр пилочный + педикюр пилочный + плёнки",
        "category": "combo",
        "price": 7500,
        "duration": 150,
        "desc": "Бережный уход и долговременный результат",
        "bullets": ["обработка без травм", "аккуратная форма ногтей", "долговременное покрытие"],
    },
    {
        "id": "file_manicure",
        "name": "Пилочный маникюр",
        "category": "manicure",
        "price": 2500,
        "duration": 60,
        "desc": "Бережный уход и естественный результат",
        "bullets": ["обработка без травм", "аккуратная форма ногтей", "уход за кожей рук"],
    },
    {
        "id": "file_manicure_spa",
        "name": "Пилочный маникюр + SPA",
        "category": "manicure",
        "price": 3000,
        "duration": 90,
        "desc": "Глубокий уход и расслабление",
        "bullets": ["мягкий уход", "увлажнение", "расслабление"],
    },
    {
        "id": "file_manicure_films",
        "name": "Пилочный маникюр + плёнки",
        "category": "manicure",
        "price": 4000,
        "duration": 90,
        "desc": "Дизайн без вреда для ногтей",
        "bullets": ["бережная обработка", "дизайн плёнками", "аккуратный результат"],
    },
    {
        "id": "file_manicure_lacquer",
        "name": "Пилочный маникюр + лак",
        "category": "manicure",
        "price": 3500,
        "duration": 60,
        "desc": "Классическое покрытие с уходом",
        "bullets": ["аккуратная форма", "классическое покрытие", "бережный уход"],
    },
    {
        "id": "file_manicure_gel_lacquer",
        "name": "Пилочный маникюр + гель-лак",
        "category": "manicure",
        "price": 5500,
        "duration": 120,
        "desc": "Долговременный результат без сколов",
        "bullets": ["стойкое покрытие", "бережная обработка", "аккуратный результат"],
    },
    {
        "id": "file_pedicure",
        "name": "Пилочный педикюр",
        "category": "pedicure",
        "price": 3500,
        "duration": 90,
        "desc": "Аккуратный уход за стопами и ногтями",
        "bullets": ["уход за стопами", "аккуратная обработка", "комфорт"],
    },
    {
        "id": "file_pedicure_toes",
        "name": "Пилочный педикюр: обработка пальчиков",
        "category": "pedicure",
        "price": 2500,
        "duration": 45,
        "desc": "Аккуратный уход за ногтями",
        "bullets": ["обработка пальчиков", "аккуратная форма", "бережный уход"],
    },
    {
        "id": "file_pedicure_spa",
        "name": "Пилочный педикюр + SPA",
        "category": "pedicure",
        "price": 4500,
        "duration": 120,
        "desc": "Глубокое восстановление и уход",
        "bullets": ["SPA-уход", "восстановление кожи", "комфорт"],
    },
    {
        "id": "file_pedicure_films",
        "name": "Пилочный педикюр + плёнки",
        "category": "pedicure",
        "price": 5000,
        "duration": 90,
        "desc": "Уход и дизайн в одной процедуре",
        "bullets": ["бережный педикюр", "дизайн плёнками", "долговременный результат"],
    },
    {
        "id": "file_pedicure_lacquer",
        "name": "Пилочный педикюр + лак",
        "category": "pedicure",
        "price": 4500,
        "duration": 90,
        "desc": "Классический педикюр с покрытием",
        "bullets": ["аккуратная обработка", "классическое покрытие", "уход"],
    },
    {
        "id": "spa_hands_feet",
        "name": "SPA-уход для рук / ног",
        "category": "extra",
        "price": 1000,
        "duration": 30,
        "desc": "Дополнительное питание и восстановление",
        "bullets": ["питание кожи", "восстановление", "мягкость"],
    },
    {
        "id": "gel_lacquer_removal",
        "name": "Полное снятие гель-лака",
        "category": "extra",
        "price": 1000,
        "duration": 30,
        "desc": "Безопасное удаление покрытия",
        "bullets": ["безопасное снятие", "бережно к ногтям", "без травм"],
    },
    {
        "id": "gel_strengthening",
        "name": "Укрепление гелем",
        "category": "extra",
        "price": 1500,
        "duration": 30,
        "desc": "Усиление натуральных ногтей",
        "bullets": ["укрепление", "защита ногтей", "долговременный результат"],
    },
]


def get_service(service_id: str):
    for service in SERVICES:
        if service["id"] == service_id:
            return service
    return None


def get_services_by_ids(service_ids: list[str]):
    result = []

    for service_id in service_ids:
        service = get_service(service_id)
        if not service:
            raise ValueError(f"Unknown service_id: {service_id}")
        result.append(service)

    return result


def build_combined_service(service_ids: list[str]):
    services = get_services_by_ids(service_ids)

    return {
        "id": "+".join([s["id"] for s in services]),
        "ids": [s["id"] for s in services],
        "name": " + ".join([s["name"] for s in services]),
        "duration": sum(int(s["duration"]) for s in services),
        "price": sum(int(s["price"]) for s in services),
        "services": services,
    }
