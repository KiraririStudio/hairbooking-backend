from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import sqlite3
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://brain0820.github.io"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


DB_NAME = "data.db"

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            phone TEXT,
            pay_code TEXT,
            date TEXT,
            time TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

class Reservation(BaseModel):
    name: str
    phone: str
    paycode: str
    date: str
    time: str


@app.get("/_debug/db")
def debug_db():
    return {
        "DATABASE_URL": os.environ.get("DATABASE_URL"),
        "DB_TYPE": "postgresql" if os.environ.get("DATABASE_URL", "").startswith("postgresql") else "sqlite"
    }

@app.post("/reserve")
def reserve(r: Reservation):
    conn = get_db()
    cur = conn.execute(
        "SELECT COUNT(*) FROM reservations WHERE date=? AND time=?",
        (r.date, r.time)
    )
    count = cur.fetchone()[0]

    if count >= 2:
        conn.close()
        raise HTTPException(status_code=400, detail="此時段已滿")

    conn.execute(
        """
        INSERT INTO reservations (name, phone, pay_code, date, time, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (r.name, r.phone, r.paycode, r.date, r.time, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

    return {"message": "預約成功"}

@app.get("/admin", response_class=HTMLResponse)
def admin():
    conn = get_db()

    rows = conn.execute("""
        SELECT date, time, name, phone, pay_code
        FROM reservations
        ORDER BY date, time, created_at
    """).fetchall()

    conn.close()

    # 將資料整理成：
    # {(date, time): [(name, phone, pay_code), ...]}
    data = {}
    for r in rows:
        key = (r["date"], r["time"])
        data.setdefault(key, []).append(
            (r["name"], r["phone"], r["pay_code"])
        )

    html = """
    <html>
    <head>
        <meta charset="utf-8">
        <title>預約後台</title>
        <style>
            body { font-family: Arial; padding: 30px; }
            table {
                border-collapse: collapse;
                width: 100%;
            }
            th, td {
                border: 1px solid #000;
                padding: 8px;
                vertical-align: top;
            }
            th {
                background-color: #f0f0f0;
            }
            .person {
                margin-bottom: 6px;
            }
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
        count = len(people)

        html += f"""
        <tr>
            <td>{date}</td>
            <td>{time}</td>
            <td>{count} / 2</td>
            <td>
        """

        for idx, (name, phone, code) in enumerate(people, start=1):
            html += f"""
            <div class="person">
                {idx}. {name}｜{phone}｜匯款碼：{code}
            </div>
            """

        html += """
            </td>
        </tr>
        """

    html += """
        </table>
    </body>
    </html>
    """

    return html
