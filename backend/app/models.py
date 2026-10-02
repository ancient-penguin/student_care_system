from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.timeutil import utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(String(16))  # student / teacher
    name: Mapped[str] = mapped_column(String(100))
    login_code: Mapped[str] = mapped_column(String(64), unique=True)
    pin_hash: Mapped[str | None] = mapped_column(String(255))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    link_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    link_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuthSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()


class Passage(Base):
    __tablename__ = "passages"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(255), default="")
    text: Mapped[str] = mapped_column(Text)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    items: Mapped[list["Item"]] = relationship(
        back_populates="passage", order_by="Item.no", cascade="all, delete-orphan"
    )


class Item(Base):
    __tablename__ = "items"
    __table_args__ = (UniqueConstraint("passage_id", "no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    passage_id: Mapped[str] = mapped_column(ForeignKey("passages.id", ondelete="CASCADE"), index=True)
    no: Mapped[int] = mapped_column(Integer)
    choice: Mapped[str] = mapped_column(String(255))
    is_correct: Mapped[bool] = mapped_column(Boolean)
    tag: Mapped[str] = mapped_column(String(64))
    model_slots: Mapped[dict] = mapped_column(JSON, default=dict)
    explanation: Mapped[str] = mapped_column(Text, default="")
    context: Mapped[str | None] = mapped_column(Text)

    passage: Mapped[Passage] = relationship(back_populates="items")


class Template(Base):
    __tablename__ = "templates"
    __table_args__ = (UniqueConstraint("kind", "tag", "judgement"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    tag: Mapped[str] = mapped_column(String(64))
    judgement: Mapped[str] = mapped_column(String(8))  # wrong / right
    body: Mapped[str] = mapped_column(Text)
    slots: Mapped[dict] = mapped_column(JSON)  # {"name": "text" | [보기...]}


class QuestionSet(Base):
    __tablename__ = "question_sets"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    mode: Mapped[str] = mapped_column(String(16), default="shuffle")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    passages: Mapped[list["QuestionSetPassage"]] = relationship(
        order_by="QuestionSetPassage.order", cascade="all, delete-orphan"
    )


class QuestionSetPassage(Base):
    __tablename__ = "question_set_passages"

    set_id: Mapped[int] = mapped_column(ForeignKey("question_sets.id", ondelete="CASCADE"), primary_key=True)
    passage_id: Mapped[str] = mapped_column(ForeignKey("passages.id"), primary_key=True)
    order: Mapped[int] = mapped_column(Integer)


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    set_id: Mapped[int] = mapped_column(ForeignKey("question_sets.id"))
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_late: Mapped[bool] = mapped_column(Boolean, default=False)
    item_order: Mapped[list] = mapped_column(JSON)

    student: Mapped[User] = relationship()
    question_set: Mapped[QuestionSet] = relationship()
    answers: Mapped[list["Answer"]] = relationship(back_populates="assignment")


class Answer(Base):
    __tablename__ = "answers"
    __table_args__ = (UniqueConstraint("assignment_id", "item_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    judgement: Mapped[bool] = mapped_column(Boolean)  # 문법상 맞다 = true
    tag: Mapped[str] = mapped_column(String(64))
    slots: Mapped[dict] = mapped_column(JSON)
    # created_at: 처음 완료(저장)한 시각. 선생님 화면의 시작 시각/일자별 저장 건수에 쓴다.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    duration_sec: Mapped[int] = mapped_column(Integer, default=0)
    judgement_ok: Mapped[bool | None] = mapped_column(Boolean)
    tag_ok: Mapped[bool | None] = mapped_column(Boolean)
    slots_check: Mapped[dict | None] = mapped_column(JSON)

    assignment: Mapped[Assignment] = relationship(back_populates="answers")
    item: Mapped[Item] = relationship()
    review: Mapped["Review | None"] = relationship(back_populates="answer", uselist=False)


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    answer_id: Mapped[int] = mapped_column(ForeignKey("answers.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(16))  # ok / needs_work
    comment: Mapped[str | None] = mapped_column(Text)  # 2차
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    answer: Mapped[Answer] = relationship(back_populates="review")
