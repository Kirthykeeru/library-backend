from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class BookCreate(BaseModel):
    title: str
    author: str
    isbn: str = Field(min_length=10, max_length=13)
    total_copies: int = Field(gt=0)
    available_copies: int = Field(ge=0)


class BookOut(BookCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


class MemberCreate(BaseModel):
    name: str
    email: EmailStr
    member_id: str


class MemberOut(MemberCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


class BorrowCreate(BaseModel):
    book_id: int
    member_id: int


# Nested schema: `book` and `member` are full BookOut/MemberOut objects,
# not just ids. FastAPI/Pydantic resolves this by reading record.book and
# record.member off the ORM object (thanks to the relationship() we set
# up in models.py) and serializing each through its own schema.
class BorrowRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    book: BookOut
    member: MemberOut
    borrowed_at: datetime
    due_date: datetime
    returned_at: datetime | None


class UserCreate(BaseModel):
    username: str
    password: str = Field(min_length=8)
    role: Literal["staff", "student"]
    # Required only when role == "student" (validated in the endpoint,
    # since Pydantic can't easily express "required if this other field
    # equals X" without a custom validator). Used to create the linked
    # Member profile so a student can borrow immediately after signing up.
    name: str | None = None
    email: EmailStr | None = None
    member_id: str | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
