import os
from dotenv import load_dotenv

load_dotenv()

WORK_START = 10
WORK_END = 20

SLOT_STEP_MINUTES = 30
BUFFER_MINUTES = 30
BOOKING_DAYS_AHEAD = 30

CALENDAR_ID = os.getenv("CALENDAR_ID", "test_calendar")
