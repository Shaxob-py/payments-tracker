from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator


def _clean(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    v = v.strip()
    if not v:
        raise ValueError("не может быть пустым")
    return v


class StudentCreate(BaseModel):
    name: str = Field(max_length=200)
    phone: str = Field(max_length=32)
    group: str = Field(max_length=100)
    monthly_fee: int = Field(ge=0, description="Месячная сумма оплаты (целое, в минимальных единицах/сумах)")

    @field_validator("name", "phone", "group")
    @classmethod
    def strip_nonempty(cls, v):
        return _clean(v)


class StudentUpdate(BaseModel):
    """Все поля необязательные: меняются только переданные."""
    name: Optional[str] = Field(default=None, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=32)
    group: Optional[str] = Field(default=None, max_length=100)
    monthly_fee: Optional[int] = Field(default=None, ge=0)

    @field_validator("name", "phone", "group")
    @classmethod
    def strip_nonempty(cls, v):
        return _clean(v)


class Student(BaseModel):
    id: int
    name: str
    phone: str
    group: str
    monthly_fee: int


class PaymentCreate(BaseModel):
    student_id: int
    amount: int = Field(gt=0)
    paid_at: Optional[date] = None  # по умолчанию — сегодня


class Payment(BaseModel):
    id: int
    student_id: int
    amount: int
    paid_at: date


class Debtor(BaseModel):
    student_id: int
    name: str
    phone: str
    group: str
    monthly_fee: int
    paid: int
    debt: int
