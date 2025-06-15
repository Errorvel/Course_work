import logging
import asyncio
from datetime import datetime, timedelta
import csv
import matplotlib.pyplot as plt
from io import BytesIO, StringIO

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BufferedInputFile
)

from config import API_TOKEN, POLLING_TIMEOUT, PIE_CHART_DPI, CATEGORIES, get_main_kb
from db import add_task, finish_task, fetch_tasks


logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


active_tasks: dict[int, list[tuple[int, str]]] = {}


async def make_pie_file(data: list[tuple[str, int]]) -> BufferedInputFile:

    fig, ax = plt.subplots(dpi=PIE_CHART_DPI)
    labels, sizes = zip(*data) if data else ([], [])
    ax.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=90)
    ax.axis('equal')

    buf = BytesIO()
    plt.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return BufferedInputFile(buf.read(), filename="chart.png")


@dp.message(Command("start"))
async def cmd_start(m: Message):
    await m.answer(
        "Привет! Я бот для учёта твоего времени.",
        reply_markup=get_main_kb()
    )


@dp.message(F.text == "🎯 Начать задачу")
async def start_task(m: Message):
    ikb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=cat, callback_data=f"start|{cat}")]
        for cat in CATEGORIES
    ])
    await m.answer("Выбери категорию задачи:", reply_markup=ikb)


@dp.callback_query(F.data.startswith("start|"))
async def on_category_selected(cb: CallbackQuery):
    user_id = cb.from_user.id
    user_name = cb.from_user.full_name or ""
    category = cb.data.split("|", 1)[1]
    start_iso = datetime.now().isoformat()

    task_id = add_task(user_id, user_name, category, start_iso)
    active_tasks.setdefault(user_id, []).append((task_id, category))

    await cb.answer()
    await bot.send_message(
        user_id,
        f"Задача <b>{category}</b> начата в <i>{start_iso[11:19]}</i>"
    )

    rem_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{mins} мин", callback_data=f"remind|{task_id}|{mins}")]
        for mins in (15, 30, 60)
    ])
    await bot.send_message(user_id, "🔔 Установить напоминание по задаче?", reply_markup=rem_kb)


@dp.callback_query(F.data.startswith("remind|"))
async def on_remind_set(cb: CallbackQuery):
    _, task_id_str, minutes_str = cb.data.split("|")
    user_id = cb.from_user.id
    minutes = int(minutes_str)

    await cb.answer()
    await bot.send_message(user_id, f"Напомню через {minutes} минут.")
    asyncio.create_task(reminder(user_id, int(task_id_str), minutes))


async def reminder(user_id: int, task_id: int, minutes: int):
    await asyncio.sleep(minutes * 60)
    tasks = active_tasks.get(user_id, [])
    for tid, cat in tasks:
        if tid == task_id:
            await bot.send_message(user_id, f"⏰ Напоминание по задаче <b>{cat}</b>.")
            return


@dp.message(F.text == "✅ Завершить задачу")
async def end_task(m: Message):
    user_id = m.from_user.id
    tasks = active_tasks.get(user_id)

    if not tasks:
        return await m.answer("Нет активных задач.", reply_markup=get_main_kb())

    ikb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{cat} #{tid}", callback_data=f"end|{tid}")]
        for (tid, cat) in tasks
    ])
    await m.answer("Выбери задачу для завершения:", reply_markup=ikb)


@dp.callback_query(F.data.startswith("end|"))
async def end_task_choice(cb: CallbackQuery):
    user_id = cb.from_user.id
    task_id = int(cb.data.split("|")[1])
    end_iso = datetime.now().isoformat()

    duration = finish_task(task_id, end_iso)

    tasks = active_tasks.get(user_id, [])
    active_tasks[user_id] = [t for t in tasks if t[0] != task_id]
    if not active_tasks[user_id]:
        active_tasks.pop(user_id)

    await cb.answer()
    await cb.message.answer(
        f"Задача завершена. Длительность: <b>{duration} минут</b>",
        reply_markup=get_main_kb()
    )


@dp.message(F.text == "📊 Статистика")
async def stats_menu(m: Message):
    ikb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 День", callback_data="stats|daily"),
            InlineKeyboardButton(text="🗓 Неделя", callback_data="stats|weekly"),
            InlineKeyboardButton(text="📆 Месяц", callback_data="stats|monthly")
        ]
    ])
    await m.answer("Выбери период статистики:", reply_markup=ikb)


@dp.callback_query(F.data.startswith("stats|"))
async def stats_callback(cb: CallbackQuery):
    period = cb.data.split("|")[1]
    now = datetime.now()

    if period == "daily":
        since = now - timedelta(days=1)
    elif period == "weekly":
        since = now - timedelta(days=7)
    else:
        since = now - timedelta(days=30)

    rows = fetch_tasks(cb.from_user.id, since.isoformat())
    agg = {cat: sum(dur or 0 for c, dur, *_ in rows if c == cat) for cat in CATEGORIES}
    data = [(cat, agg[cat]) for cat in CATEGORIES if agg.get(cat)]

    if data:
        chart = await make_pie_file(data)
        await cb.message.answer_photo(photo=chart)
    else:
        await cb.message.answer("Нет данных за выбранный период.")

    await cb.answer()


@dp.message(F.text == "💡 Рекомендации")
async def recommendations(m: Message):
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    rows = fetch_tasks(m.from_user.id, week_ago)

    if not rows:
        return await m.answer("Пока нет данных для рекомендаций. Начни использовать бота активнее!")

    totals = {}
    for cat, dur, *_ in rows:
        totals[cat] = totals.get(cat, 0) + (dur or 0)

    if not totals:
        return await m.answer("Нет данных для анализа.")

    max_cat = max(totals, key=totals.get)
    min_cat = min(totals, key=totals.get)

    msg = (
        f"💡 <b>Рекомендации</b>:\n"
        f"🔸 Ты много времени проводишь в категории: <b>{max_cat}</b> ({totals[max_cat]} мин).\n"
        f"🔸 Меньше всего времени ты уделяешь: <b>{min_cat}</b> ({totals[min_cat]} мин).\n"
    )
    if min_cat in ["Отдых", "Учёба"]:
        msg += f"✅ Совет: попробуй уделить больше внимания категории <b>{min_cat}</b> для баланса!"
    else:
        msg += f"✅ Совет: подумай, стоит ли уделять столько времени категории <b>{max_cat}</b>."

    await m.answer(msg, reply_markup=get_main_kb())


@dp.message(Command("export"))
async def export_data(m: Message):
    rows = fetch_tasks(m.from_user.id, "1970-01-01T00:00:00")
    data = [["Категория", "Начало", "Конец", "Минуты"]]

    for cat, dur, start, end in rows:
        data.append([cat, start, end or "", str(dur or 0)])

    buf = StringIO()
    csv.writer(buf).writerows(data)
    bom = ("\ufeff" + buf.getvalue()).encode('utf-8')

    await m.answer_document(document=BufferedInputFile(bom, filename="export.csv"))


async def main():
    await dp.start_polling(bot, timeout=POLLING_TIMEOUT)


if __name__ == "__main__":
    asyncio.run(main())
