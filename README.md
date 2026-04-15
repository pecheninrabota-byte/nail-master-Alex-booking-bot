# Nail Master Booking Bot

Backend для сайта мастера маникюра.

## Что умеет сейчас
- отдаёт список услуг
- отдаёт FAQ
- генерирует доступные слоты
- принимает тестовую запись

## Запуск локально

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
