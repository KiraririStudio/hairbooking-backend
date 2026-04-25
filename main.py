from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import psycopg2
import os

app = FastAPI()

# ===== CORS =====
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://kirariristudio.github.io"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== PostgreSQL =====
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not set")
    return psycopg2.connect(DATABASE_URL)

# ===== 初始化資料表 =====
def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reservations (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            pay_code TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

if DATABASE_URL:
    init_db()

# ===== Models =====
class Reservation(BaseModel):
    name: str
    phone: str
    paycode: str
    date: str
    time: str


# ======================================================
# ✅ 預約規則設定
# ======================================================

AVAILABLE_DATES = [
    "2026-04-24", "2026-04-26", "2026-04-29",
    "2026-05-01", "2026-05-02", "2026-05-06",
    "2026-05-08", "2026-05-09", "2026-05-10",
    "2026-05-13", "2026-05-15", "2026-05-16",
    "2026-05-17", "2026-05-20", "2026-05-22",
    "2026-05-23", "2026-05-24", "2026-05-27",
    "2026-05-29", "2026-05-30"
]

SPECIAL_TIME_RULES = {
    "2026-04-24": ("14:00", "18:00"),
    "2026-05-02": ("13:00", "17:00"),
    "2026-05-16": ("13:00", "17:00"),
    "2026-05-30": ("13:00", "17:00"),
}

DEFAULT_START = "13:00"
DEFAULT_END = "18:00"

TZ = ZoneInfo("Asia/Taipei")


# ======================================================
# ✅ 共用工具
# ======================================================

def get_reservation_count_by_date(date_str: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT time, COUNT(*)
        FROM reservations
        WHERE date = %s
        GROUP BY time
    """, (date_str,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {time: count for time, count in rows}

def generate_times(start_str, end_str):
    start = datetime.strptime(start_str, "%H:%M")
    end = datetime.strptime(end_str, "%H:%M")
    times = []
    current = start
    while current < end:
        times.append(current.strftime("%H:%M"))
        current += timedelta(minutes=20)
    return times


# ======================================================
# ✅ 前台 API
# ======================================================

@app.get("/available-dates")
def available_dates():
    now = datetime.now(TZ)
    today_str = now.strftime("%Y-%m-%d")

    results = []
    for d in AVAILABLE_DATES:
        if d < today_str:
            continue

        start, end = SPECIAL_TIME_RULES.get(d, (DEFAULT_START, DEFAULT_END))
        all_times = generate_times(start, end)

        if d == today_str:
            current_time_str = now.strftime("%H:%M")
            all_times = [t for t in all_times if t > current_time_str]

            if not all_times:
                continue

        counts = get_reservation_count_by_date(d)

        if all(counts.get(t, 0) >= 1 for t in all_times):
            continue

        results.append({"value": d})

    return results


@app.get("/available-times")
def available_times(date: str):
    now = datetime.now(TZ)
    today_str = now.strftime("%Y-%m-%d")

    start, end = SPECIAL_TIME_RULES.get(date, (DEFAULT_START, DEFAULT_END))
    all_times = generate_times(start, end)

    if date == today_str:
        current_time_str = now.strftime("%H:%M")
        all_times = [t for t in all_times if t > current_time_str]

    counts = get_reservation_count_by_date(date)
    return [t for t in all_times if counts.get(t, 0) < 1]


# ======================================================
# ✅ 新增預約（每時段只允許 1 人）
# ======================================================

@app.post("/reserve")
def reserve(r: Reservation):
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT COUNT(*) FROM reservations WHERE date=%s AND time=%s",
        (r.date, r.time)
    )

    if cur.fetchone()[0] >= 1:
        raise HTTPException(status_code=400, detail="此時段已滿")

    cur.execute("""
        INSERT INTO reservations (name, phone, pay_code, date, time, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (r.name, r.phone, r.paycode, r.date, r.time, datetime.now()))

    conn.commit()
    cur.close()
    conn.close()

    return {"message": "預約成功"}


# ======================================================
# ✅ 後台刪除單筆預約
# ======================================================

@app.post("/admin/delete/{reservation_id}")
def delete_reservation(reservation_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM reservations WHERE id = %s", (reservation_id,))
    conn.commit()
    cur.close()
    conn.close()
    return RedirectResponse(url="/admin", status_code=303)


# ======================================================
# ✅ 後台顯示
# ======================================================

@app.get("/admin", response_class=HTMLResponse)
def admin():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, date, time, name, phone, pay_code
        FROM reservations
        ORDER BY date, time, created_at
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    data = {}
    for rid, date, time, name, phone, code in rows:
        data.setdefault((date, time), []).append(
            {"id": rid, "name": name, "phone": phone, "code": code}
        )

    html = """
    <html><head><meta charset="utf-8">
    <title>預約後台</title>
    <style>
    body { font-family: Arial; padding: 30px; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #000; padding: 8px; vertical-align: top; }
    th { background-color: #f0f0f0; }
    form { display: inline; }
    button { margin-left: 8px; }
    </style></head><body>
    <h2>預約狀態</h2>
    <table>
      <tr>
        <th>日期</th>
        <th>時間</th>
        <th>人數</th>
        <th>名單</th>
      </tr>
    """

    for (date, time), people in data.items():
        html += f"<tr><td>{date}</td><td>{time}</td>"
        html += f"<td>{len(people)} / 1</td><td>"

        
    for idx, p in enumerate(people, 1):
        html += f"""
        {idx}. {p['name']}｜{p['phone']}｜{p['code']}
        <form method="post" action="/admin/delete/{p['id']}"
              onsubmit="return confirm('確定要刪除這筆預約嗎？');">
            <button type="submit">刪除</button>
        </form><br>
        """


        html += "</td></tr>"

    html += "</table></body></html>"
    return html
