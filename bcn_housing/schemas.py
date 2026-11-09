import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


TransactionType = Literal["BUY", "RENT"]
LeadStatus = Literal[
    "NEW", "REVIEWING", "MATCHED", "CONTACTED", "VIEWING_SCHEDULED", "CONVERTED", "CLOSED"
]
DataLabel = Literal["DEMO", "REAL"]
PropertyStatus = Literal["AVAILABLE", "UNAVAILABLE", "CLOSED"]
ViewingStatus = Literal["NEW", "SCHEDULED", "COMPLETED", "CANCELLED"]


class RequirementCreate(BaseModel):
    transaction_type: TransactionType
    budget_min: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    budget_max: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    preferred_locations: list[str] = Field(default_factory=list, max_length=20)
    property_type: str | None = Field(default=None, max_length=80)
    bedrooms_min: int | None = Field(default=None, ge=0, le=20)
    area_min_sqm: float | None = Field(default=None, gt=0, le=10000, allow_inf_nan=False)
    timeline: str | None = Field(default=None, max_length=200)
    additional_requirements: str | None = Field(default=None, max_length=3000)
    preferred_language: str = Field(default="zh", min_length=2, max_length=20)
    contact_name: str = Field(min_length=1, max_length=160)
    contact_email: str | None = Field(default=None, max_length=254)
    contact_phone: str | None = Field(default=None, max_length=40)

    @field_validator("contact_email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
                raise ValueError("Invalid email address")
        return value

    @field_validator("contact_phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            if not re.fullmatch(r"[+()\d.\-\s]{6,40}", value) or sum(char.isdigit() for char in value) < 6:
                raise ValueError("Invalid phone number")
        return value

    @field_validator("preferred_locations")
    @classmethod
    def clean_locations(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if any(len(item) > 160 for item in cleaned):
            raise ValueError("Location names must be at most 160 characters")
        return cleaned

    @model_validator(mode="after")
    def validate_budget_and_contact(self) -> "RequirementCreate":
        if self.budget_min is not None and self.budget_max is not None and self.budget_min > self.budget_max:
            raise ValueError("budget_min cannot exceed budget_max")
        if not self.contact_email and not self.contact_phone:
            raise ValueError("Provide at least one contact method")
        return self


class PropertyCreate(BaseModel):
    transaction_type: TransactionType
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=3000)
    location: str = Field(min_length=1, max_length=160)
    neighborhood: str | None = Field(default=None, max_length=160)
    price: float = Field(gt=0, le=1_000_000_000, allow_inf_nan=False)
    area_sqm: float = Field(gt=0, le=10000, allow_inf_nan=False)
    bedrooms: int | None = Field(default=None, ge=0, le=50)
    bathrooms: int | None = Field(default=None, ge=0, le=50)
    property_type: str = Field(min_length=1, max_length=80)
    condition: str | None = Field(default=None, max_length=80)
    floor: str | None = Field(default=None, max_length=40)
    has_elevator: bool | None = None
    images: list[str] = Field(default_factory=list, max_length=10)
    source: str | None = Field(default=None, max_length=200)
    data_label: DataLabel = "DEMO"
    status: PropertyStatus = "AVAILABLE"

    @field_validator("images")
    @classmethod
    def validate_image_refs(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value.strip() or len(value) > 2048:
                raise ValueError("Image references must be non-empty and at most 2048 characters")
        return values


class PropertyStatusUpdate(BaseModel):
    status: PropertyStatus


class AgentCreate(BaseModel):
    profile_type: Literal["AGENCY", "INDEPENDENT"]
    name: str = Field(min_length=1, max_length=160)
    agency_name: str | None = Field(default=None, max_length=160)
    service_areas: list[str] = Field(default_factory=list, max_length=30)
    specializations: list[TransactionType] = Field(min_length=1, max_length=2)
    languages: list[str] = Field(default_factory=list, max_length=20)
    contact_email: str | None = Field(default=None, max_length=254)
    contact_phone: str | None = Field(default=None, max_length=40)
    verified: bool = False
    active: bool = True

    @field_validator("contact_email")
    @classmethod
    def validate_agent_email(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
                raise ValueError("Invalid email address")
        return value

    @field_validator("contact_phone")
    @classmethod
    def validate_agent_phone(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            if not re.fullmatch(r"[+()\d.\-\s]{6,40}", value) or sum(char.isdigit() for char in value) < 6:
                raise ValueError("Invalid phone number")
        return value


class AgentStatusUpdate(BaseModel):
    active: bool
    verified: bool | None = None


class AdminLogin(BaseModel):
    username: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=1, max_length=1024)


class AgentAssignment(BaseModel):
    agent_id: str


class LeadStatusUpdate(BaseModel):
    status: LeadStatus


class LeadNoteCreate(BaseModel):
    note: str = Field(min_length=1, max_length=2000)

    @field_validator("note")
    @classmethod
    def clean_note(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Note cannot be blank")
        return value


class ViewingCreate(BaseModel):
    requirement_id: str
    property_id: str
    preferred_at: datetime | None = None
    customer_notes: str | None = Field(default=None, max_length=2000)


class ViewingUpdate(BaseModel):
    status: ViewingStatus
    assigned_agent_id: str | None = None
    preferred_at: datetime | None = None
    report_references: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("report_references")
    @classmethod
    def validate_report_refs(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 2048 for value in values):
            raise ValueError("Report references must be non-empty and at most 2048 characters")
        return values
