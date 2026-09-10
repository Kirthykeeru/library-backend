from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from database import Base


class BookModel(Base):
    __tablename__ = "books"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    author = Column(String, nullable=False)
    isbn = Column(String, unique=True, nullable=False)
    total_copies = Column(Integer, nullable=False)
    available_copies = Column(Integer, nullable=False)


class MemberModel(Base):
    __tablename__ = "members"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    member_id = Column(String, unique=True, nullable=False)
    # Links a member record to the login account that owns it. Nullable
    # because staff-created members (Stage 3) may not have a user account,
    # and staff accounts don't have a member record at all.
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=True)


class UserModel(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False)  # "staff" or "student"


class BorrowRecordModel(Base):
    __tablename__ = "borrow_records"

    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(Integer, ForeignKey("books.id"), nullable=False)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=False)
    borrowed_at = Column(DateTime, nullable=False)
    due_date = Column(DateTime, nullable=False)
    returned_at = Column(DateTime, nullable=True)  # NULL while still checked out

    # relationship() lets us do record.book / record.member in Python and
    # get the full BookModel/MemberModel object via a SQL join, instead of
    # manually looking them up by book_id/member_id every time.
    book = relationship("BookModel")
    member = relationship("MemberModel")
