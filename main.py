import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

import auth
import models
from database import Base, engine, get_db
from schemas import (
    BookCreate,
    BookOut,
    BorrowCreate,
    BorrowRecordOut,
    MemberCreate,
    MemberOut,
    Token,
    UserCreate,
    UserOut,
)

BORROW_PERIOD_DAYS = 14

# Creates tables from the models in models.py if they don't already exist.
# In a real project you'd use a migration tool (Alembic) instead of this,
# but create_all is the standard way to bootstrap a dev database.
Base.metadata.create_all(bind=engine)

app = FastAPI(title="College Library Management System")

# Allows the React dev server (different origin/port) to call this API.
# In production, set CORS_ORIGINS to the actual deployed frontend URL(s),
# comma-separated.
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"message": "Welcome to the Library API"}


# ---------- Auth ----------

@app.post("/auth/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(user: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.UserModel).filter(models.UserModel.username == user.username).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already taken")

    if user.role == "student":
        if not (user.name and user.email and user.member_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Student registration requires name, email, and member_id",
            )
        member_conflict = (
            db.query(models.MemberModel)
            .filter(
                (models.MemberModel.email == user.email)
                | (models.MemberModel.member_id == user.member_id)
            )
            .first()
        )
        if member_conflict is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Member email or member_id already registered",
            )

    new_user = models.UserModel(
        username=user.username,
        hashed_password=auth.hash_password(user.password),
        role=user.role,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    if user.role == "student":
        new_member = models.MemberModel(
            name=user.name,
            email=user.email,
            member_id=user.member_id,
            user_id=new_user.id,
        )
        db.add(new_member)
        db.commit()

    return new_user


# OAuth2PasswordRequestForm expects standard form fields (username, password),
# not JSON — this is what lets the /docs "Authorize" button work out of the box.
@app.post("/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.UserModel).filter(models.UserModel.username == form_data.username).first()
    if user is None or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = auth.create_access_token(data={"sub": user.username})
    return Token(access_token=access_token)


@app.get("/auth/me", response_model=UserOut)
def me(current_user: models.UserModel = Depends(auth.get_current_user)):
    return current_user


# ---------- Books ----------

@app.get("/books", response_model=list[BookOut])
def list_books(db: Session = Depends(get_db)):
    return db.query(models.BookModel).all()


@app.get("/books/{book_id}", response_model=BookOut)
def get_book(book_id: int, db: Session = Depends(get_db)):
    book = db.query(models.BookModel).filter(models.BookModel.id == book_id).first()
    if book is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")
    return book


@app.post("/books", response_model=BookOut, status_code=status.HTTP_201_CREATED)
def create_book(
    book: BookCreate,
    db: Session = Depends(get_db),
    _staff: models.UserModel = Depends(auth.require_staff),
):
    existing = db.query(models.BookModel).filter(models.BookModel.isbn == book.isbn).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A book with this ISBN already exists")

    new_book = models.BookModel(**book.model_dump())
    db.add(new_book)
    db.commit()
    db.refresh(new_book)  # pulls back the auto-generated id
    return new_book


@app.put("/books/{book_id}", response_model=BookOut)
def update_book(
    book_id: int,
    book: BookCreate,
    db: Session = Depends(get_db),
    _staff: models.UserModel = Depends(auth.require_staff),
):
    existing = db.query(models.BookModel).filter(models.BookModel.id == book_id).first()
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")

    isbn_conflict = (
        db.query(models.BookModel)
        .filter(models.BookModel.isbn == book.isbn, models.BookModel.id != book_id)
        .first()
    )
    if isbn_conflict is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A book with this ISBN already exists")

    for field, value in book.model_dump().items():
        setattr(existing, field, value)
    db.commit()
    db.refresh(existing)
    return existing


@app.delete("/books/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_book(
    book_id: int,
    db: Session = Depends(get_db),
    _staff: models.UserModel = Depends(auth.require_staff),
):
    existing = db.query(models.BookModel).filter(models.BookModel.id == book_id).first()
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")
    db.delete(existing)
    db.commit()


# ---------- Members ----------

@app.get("/members", response_model=list[MemberOut])
def list_members(
    db: Session = Depends(get_db),
    _staff: models.UserModel = Depends(auth.require_staff),
):
    return db.query(models.MemberModel).all()


@app.get("/members/me", response_model=MemberOut)
def get_my_member_profile(
    db: Session = Depends(get_db),
    current_user: models.UserModel = Depends(auth.get_current_user),
):
    member = db.query(models.MemberModel).filter(models.MemberModel.user_id == current_user.id).first()
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No member profile linked to this account",
        )
    return member


# Note: this route is registered AFTER /members/me above. FastAPI/Starlette
# matches routes in registration order, so if /members/{member_id} came
# first, a request to /members/me would match it first and fail int
# validation on "me" instead of ever reaching the /members/me handler.
@app.get("/members/{member_id}", response_model=MemberOut)
def get_member(
    member_id: int,
    db: Session = Depends(get_db),
    _staff: models.UserModel = Depends(auth.require_staff),
):
    member = db.query(models.MemberModel).filter(models.MemberModel.id == member_id).first()
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    return member


@app.post("/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def create_member(
    member: MemberCreate,
    db: Session = Depends(get_db),
    _staff: models.UserModel = Depends(auth.require_staff),
):
    conflict = (
        db.query(models.MemberModel)
        .filter(
            (models.MemberModel.email == member.email)
            | (models.MemberModel.member_id == member.member_id)
        )
        .first()
    )
    if conflict is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A member with this email or member_id already exists",
        )

    new_member = models.MemberModel(**member.model_dump())
    db.add(new_member)
    db.commit()
    db.refresh(new_member)
    return new_member


@app.delete("/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_member(
    member_id: int,
    db: Session = Depends(get_db),
    _staff: models.UserModel = Depends(auth.require_staff),
):
    existing = db.query(models.MemberModel).filter(models.MemberModel.id == member_id).first()
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    db.delete(existing)
    db.commit()


# ---------- Borrow / Return ----------

@app.post("/borrow", response_model=BorrowRecordOut, status_code=status.HTTP_201_CREATED)
def borrow_book(
    borrow: BorrowCreate,
    db: Session = Depends(get_db),
    _user: models.UserModel = Depends(auth.get_current_user),
):
    book = db.query(models.BookModel).filter(models.BookModel.id == borrow.book_id).first()
    if book is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")

    member = db.query(models.MemberModel).filter(models.MemberModel.id == borrow.member_id).first()
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    if book.available_copies <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No copies of this book are currently available",
        )

    now = datetime.now(timezone.utc)
    record = models.BorrowRecordModel(
        book_id=book.id,
        member_id=member.id,
        borrowed_at=now,
        due_date=now + timedelta(days=BORROW_PERIOD_DAYS),
        returned_at=None,
    )
    book.available_copies -= 1

    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@app.post("/borrow/{record_id}/return", response_model=BorrowRecordOut)
def return_book(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: models.UserModel = Depends(auth.get_current_user),
):
    record = (
        db.query(models.BorrowRecordModel)
        .filter(models.BorrowRecordModel.id == record_id)
        .first()
    )
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Borrow record not found")

    # Staff can return any book (e.g. handling a walk-in return at the desk).
    # A student may only return their own borrow.
    if current_user.role != "staff" and record.member.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only return your own borrowed books",
        )

    if record.returned_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Book already returned")

    record.returned_at = datetime.now(timezone.utc)
    record.book.available_copies += 1

    db.commit()
    db.refresh(record)
    return record


@app.get("/borrow-records/mine", response_model=list[BorrowRecordOut])
def list_my_borrow_records(
    active_only: bool = False,
    db: Session = Depends(get_db),
    current_user: models.UserModel = Depends(auth.get_current_user),
):
    member = db.query(models.MemberModel).filter(models.MemberModel.user_id == current_user.id).first()
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No member profile linked to this account",
        )
    query = db.query(models.BorrowRecordModel).filter(models.BorrowRecordModel.member_id == member.id)
    if active_only:
        query = query.filter(models.BorrowRecordModel.returned_at.is_(None))
    return query.all()


@app.get("/borrow-records", response_model=list[BorrowRecordOut])
def list_borrow_records(
    active_only: bool = False,
    db: Session = Depends(get_db),
    _staff: models.UserModel = Depends(auth.require_staff),
):
    query = db.query(models.BorrowRecordModel)
    if active_only:
        query = query.filter(models.BorrowRecordModel.returned_at.is_(None))
    return query.all()
