import re
import sqlite3
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .db import get_db, init_db
from .schemas import (
    Debtor, Payment, PaymentCreate, Student, StudentCreate, StudentUpdate,
)

STATIC = Path(__file__).parent / "static"
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Учёт оплат учебного центра", lifespan=lifespan)


def _student(row: sqlite3.Row) -> Student:
    return Student(id=row["id"], name=row["name"], phone=row["phone"],
                   group=row["group_name"], monthly_fee=row["monthly_fee"])


def _get_student_or_404(db: sqlite3.Connection, student_id: int) -> sqlite3.Row:
    row = db.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Ученик не найден")
    return row


# ---------- Ученики ----------

@app.post("/students", response_model=Student, status_code=201)
def create_student(data: StudentCreate, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute(
        "INSERT INTO students (name, phone, group_name, monthly_fee) VALUES (?, ?, ?, ?)",
        (data.name, data.phone, data.group, data.monthly_fee),
    )
    db.commit()
    return _student(_get_student_or_404(db, cur.lastrowid))


@app.get("/students", response_model=List[Student])
def list_students(group: Optional[str] = None, db: sqlite3.Connection = Depends(get_db)):
    if group:
        rows = db.execute("SELECT * FROM students WHERE group_name = ? ORDER BY name", (group,))
    else:
        rows = db.execute("SELECT * FROM students ORDER BY name")
    return [_student(r) for r in rows.fetchall()]


@app.get("/students/{student_id}", response_model=Student)
def get_student(student_id: int, db: sqlite3.Connection = Depends(get_db)):
    return _student(_get_student_or_404(db, student_id))


@app.put("/students/{student_id}", response_model=Student)
def update_student(student_id: int, data: StudentUpdate, db: sqlite3.Connection = Depends(get_db)):
    current = _get_student_or_404(db, student_id)
    changes = data.model_dump(exclude_none=True)
    merged = {
        "name": changes.get("name", current["name"]),
        "phone": changes.get("phone", current["phone"]),
        "group_name": changes.get("group", current["group_name"]),
        "monthly_fee": changes.get("monthly_fee", current["monthly_fee"]),
    }
    db.execute(
        "UPDATE students SET name=?, phone=?, group_name=?, monthly_fee=? WHERE id=?",
        (merged["name"], merged["phone"], merged["group_name"], merged["monthly_fee"], student_id),
    )
    db.commit()
    return _student(_get_student_or_404(db, student_id))


@app.delete("/students/{student_id}", status_code=204)
def delete_student(student_id: int, db: sqlite3.Connection = Depends(get_db)):
    _get_student_or_404(db, student_id)
    db.execute("DELETE FROM students WHERE id = ?", (student_id,))  # оплаты удалятся каскадом
    db.commit()
    return Response(status_code=204)


# ---------- Оплаты ----------

@app.post("/payments", response_model=Payment, status_code=201)
def add_payment(data: PaymentCreate, db: sqlite3.Connection = Depends(get_db)):
    _get_student_or_404(db, data.student_id)
    paid_at = (data.paid_at or date.today()).isoformat()
    cur = db.execute(
        "INSERT INTO payments (student_id, amount, paid_at) VALUES (?, ?, ?)",
        (data.student_id, data.amount, paid_at),
    )
    db.commit()
    row = db.execute("SELECT * FROM payments WHERE id = ?", (cur.lastrowid,)).fetchone()
    return Payment(**dict(row))


@app.get("/students/{student_id}/payments", response_model=List[Payment])
def list_student_payments(student_id: int, db: sqlite3.Connection = Depends(get_db)):
    _get_student_or_404(db, student_id)
    rows = db.execute(
        "SELECT * FROM payments WHERE student_id = ? ORDER BY paid_at DESC, id DESC",
        (student_id,),
    ).fetchall()
    return [Payment(**dict(r)) for r in rows]


# ---------- Должники ----------

def _month_bounds(month: str):
    if not MONTH_RE.match(month):
        raise HTTPException(422, "month должен быть в формате YYYY-MM, например 2026-10")
    y, m = int(month[:4]), int(month[5:])
    start = date(y, m, 1)
    end = date(y + (m == 12), 1 if m == 12 else m + 1, 1)
    return start.isoformat(), end.isoformat()


@app.get("/debtors", response_model=List[Debtor])
def debtors(
    month: Optional[str] = Query(None, description="YYYY-MM; по умолчанию текущий месяц"),
    db: sqlite3.Connection = Depends(get_db),
):
    month = month or date.today().strftime("%Y-%m")
    start, end = _month_bounds(month)
    rows = db.execute(
        """
        SELECT s.id, s.name, s.phone, s.group_name, s.monthly_fee,
               COALESCE(SUM(p.amount), 0) AS paid
        FROM students s
        LEFT JOIN payments p
               ON p.student_id = s.id AND p.paid_at >= ? AND p.paid_at < ?
        GROUP BY s.id
        HAVING paid < s.monthly_fee
        ORDER BY (s.monthly_fee - paid) DESC, s.name
        """,
        (start, end),
    ).fetchall()
    return [
        Debtor(student_id=r["id"], name=r["name"], phone=r["phone"], group=r["group_name"],
               monthly_fee=r["monthly_fee"], paid=r["paid"], debt=r["monthly_fee"] - r["paid"])
        for r in rows
    ]


# ---------- Веб-страница ----------

@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
