from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import psycopg2
import os

app = FastAPI()

# ===== CORS =====
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://brain0820.github.io"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== PostgreSQL 連線 =====
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

init_db()

# ===== API Model =====
class Reservation(BaseModel):
    name: str
    phone: str
    paycode: str
    date: str
    time: str

# ===== PostgreSQL 驗證 API =====
@app.get("/_debug/db")
def debug_db():
    return {
        "DATABASE_URL_EXISTS": DATABASE_URL is not None,
        "DATABASE_URL_PREFIX": DATABASE_URL[:15] if DATABASE_URL else None,
        "DB_TYPE": "postgresql" if DATABASE_URL and DATABASE_URL.startswith("postgresql") else "sqlite"
    }

# ===== 新增預約 =====
@app.post("/reserve")
def reserve(r: Reservation):
    conn = get_db()
    cur = conn.cursor()

    # 檢查人數
    cur.execute(
        "SELECT COUNT(*) FROM reservations WHERE date=%s AND time=%s",
        (r.date, r.time)
    )
    count = cur.fetchone()[0]

    if count >= 2:
        cur.close()
        conn.close()
        raise HTTPException(status_code=400, detail="此時段已滿")

    # 寫入資料
    cur.execute(
        """
        INSERT INTO reservations (name, phone, pay_code, date, time, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (r.name, r.phone, r.paycode, r.date, r.time, datetime.now())
    )
    conn.commit()
    cur.close()
    conn.close()

    return {"message": "預約成功"}

# ===== 後台 /admin =====
@app.get("/admin", response_class=HTMLResponse)
def admin():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT date, time, name, phone, pay_code
        FROM reservations
        ORDER BY date, time, created_at
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    # 整理資料 {(date, time): [(name, phone, pay_code), ...]}
    data = {}
    for date, time, name, phone, pay_code in rows:
        key = (date, time)
        data.setdefault(key, []).append((name, phone, pay_code))

    html = """
    <html>
    <head>
        <meta charset="utf-8">
        <title>預約後台</title>
        <style>
            body { font-family: Arial; padding: 30px; }
            table { border-collapse: collapse; width: 100%; }
            th, td {
                border: 1px solid #000;
                padding: 8px;
                vertical-align: top;
            }
            th { background-color: #f0f0f0; }
            .person { margin-bottom: 6px; }
        </style>
    </head>
    <body>
        <h2>預約狀態</h2>
        <table>
            <tr>
                <th>日期</th>
                <th>時間</th>
                <th>人數</th>
                <th>預約人資料</th>
            </tr>
    """

    for (date, time), people in data.items():
        html += f"""
        <tr>
            <td>{date}</td>
            <td>{time}</td>
            <td>{len(people)} / 2</td>
            <td>
        """
        for idx, (name, phone, code) in enumerate(people, start=1):
            html += f"""
                <div class="person">
                    {idx}. {name}｜{phone}｜匯款碼：{code}
                </div>
            """
        html += "</td></tr>"

    html += """
        </table>
    </body>
    </html>
    """

    return html
