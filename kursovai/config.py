import os
from dotenv import load_dotenv
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

load_dotenv()


API_TOKEN: str = os.getenv("BOT_API_TOKEN")


POLLING_TIMEOUT: int = int(os.getenv("POLLING_TIMEOUT", 60))


PIE_CHART_DPI: int = int(os.getenv("PIE_CHART_DPI", 100))


CATEGORIES = ["Работа", "Учёба", "Отдых", "Домашние дела"]


DB_PATH: str = os.getenv("DB_PATH", "tasks.db")


_Main_kb_layout = [
    ["🎯 Начать задачу", "✅ Завершить задачу"],
    ["📊 Статистика", "💡 Рекомендации"],
    ["/export"]
]

def get_main_kb() -> ReplyKeyboardMarkup:

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=btn) for btn in row]
            for row in _Main_kb_layout
        ],
        resize_keyboard=True
    )
    return kb
