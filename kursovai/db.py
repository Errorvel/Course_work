import sqlite3
from datetime import datetime


conn = sqlite3.connect("tasks.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    user_name TEXT NOT NULL,
    category TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT,
    duration_min INTEGER
)
""")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user_start ON tasks(user_id, start_time)")
conn.commit()


def add_task(user_id: int, user_name: str, category: str, start_time: str) -> int:

    cursor.execute(
        "INSERT INTO tasks (user_id, user_name, category, start_time) VALUES (?, ?, ?, ?)",
        (user_id, user_name, category, start_time)
    )
    conn.commit()
    return cursor.lastrowid


def finish_task(task_id: int, end_time: str) -> int:

    cursor.execute("SELECT start_time FROM tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    if not row:
        return 0
    start_dt = datetime.fromisoformat(row[0])
    end_dt = datetime.fromisoformat(end_time)
    duration = int((end_dt - start_dt).total_seconds() // 60)
    cursor.execute(
        "UPDATE tasks SET end_time = ?, duration_min = ? WHERE id = ?",
        (end_time, duration, task_id)
    )
    conn.commit()
    return duration


def fetch_tasks(user_id: int, since: str) -> list[tuple]:

    cursor.execute(
        "SELECT category, duration_min, start_time, end_time FROM tasks "
        "WHERE user_id = ? AND end_time IS NOT NULL AND start_time >= ?",
        (user_id, since)
    )
    return cursor.fetchall()
def get_all_valid_named_users() -> list[tuple]:

    cursor.execute("""
        SELECT DISTINCT user_id, user_name
        FROM tasks
        WHERE user_name IS NOT NULL AND user_name != ''
    """)
    return cursor.fetchall()

