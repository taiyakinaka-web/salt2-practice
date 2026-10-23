from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Credentials(StrictModel):
    email: StrictStr = Field(max_length=254)
    password: StrictStr = Field(min_length=1, max_length=1024)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        value = value.strip().lower()
        if not value or "@" not in value or any(c.isspace() for c in value):
            raise ValueError("A valid email is required")
        if len(value.split("@")) != 2 or not all(value.split("@")):
            raise ValueError("A valid email is required")
        return value


class NewUser(Credentials):
    password: StrictStr = Field(min_length=12, max_length=1024)


class CardFields(StrictModel):
    name: StrictStr = Field(min_length=1, max_length=200)
    company_name: StrictStr = Field(default="", max_length=1000)
    department: StrictStr = Field(default="", max_length=1000)
    title: StrictStr = Field(default="", max_length=1000)
    email: StrictStr = Field(default="", max_length=1000)
    phone: StrictStr = Field(default="", max_length=1000)
    address: StrictStr = Field(default="", max_length=1000)
    website: StrictStr = Field(default="", max_length=1000)

    @field_validator("name", "company_name", "department", mode="before")
    @classmethod
    def strip_identity(cls, value):
        return value.strip() if isinstance(value, str) else value


class CardCreate(CardFields):
    request_id: UUID
    person_id: int | None = Field(default=None, gt=0, strict=True)


class GrantCreate(StrictModel):
    scope: Literal["company", "department", "person"]
    target_id: int = Field(gt=0, strict=True)
