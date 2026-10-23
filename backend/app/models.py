from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import CheckConstraint, Column, LargeBinary, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(SQLModel, table=True):
    __tablename__ = "users"
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    password_hash: str
    role: str = "user"
    created_at: datetime = Field(default_factory=utcnow)


class LoginSession(SQLModel, table=True):
    __tablename__ = "sessions"
    token_hash: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    csrf_token: str
    expires_at: datetime


class Company(SQLModel, table=True):
    __tablename__ = "companies"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True)


class Department(SQLModel, table=True):
    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("company_id", "name"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="companies.id")
    name: str


class Person(SQLModel, table=True):
    __tablename__ = "people"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str


class Card(SQLModel, table=True):
    __tablename__ = "cards"
    __table_args__ = (UniqueConstraint("created_by", "request_id"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    company_name: str = ""
    department: str = ""
    title: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""
    website: str = ""
    company_id: Optional[int] = Field(default=None, foreign_key="companies.id", index=True)
    department_id: Optional[int] = Field(default=None, foreign_key="departments.id", index=True)
    person_id: int = Field(foreign_key="people.id", index=True)
    created_by: int = Field(foreign_key="users.id", index=True)
    created_at: datetime = Field(default_factory=utcnow)
    image_bytes: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    image_mime: str
    request_id: str
    request_hash: str


class Grant(SQLModel, table=True):
    __tablename__ = "grants"
    __table_args__ = (
        UniqueConstraint("user_id", "scope", "company_id"),
        UniqueConstraint("user_id", "scope", "department_id"),
        UniqueConstraint("user_id", "scope", "person_id"),
        CheckConstraint("(scope = 'company' AND company_id IS NOT NULL AND department_id IS NULL AND person_id IS NULL) OR (scope = 'department' AND company_id IS NULL AND department_id IS NOT NULL AND person_id IS NULL) OR (scope = 'person' AND company_id IS NULL AND department_id IS NULL AND person_id IS NOT NULL)"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    scope: str
    company_id: Optional[int] = Field(default=None, foreign_key="companies.id")
    department_id: Optional[int] = Field(default=None, foreign_key="departments.id")
    person_id: Optional[int] = Field(default=None, foreign_key="people.id")
    created_at: datetime = Field(default_factory=utcnow)
