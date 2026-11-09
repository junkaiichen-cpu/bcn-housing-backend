from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from bcn_housing.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class CustomerRequirement(Base):
    __tablename__ = "customer_requirements"
    __table_args__ = (
        CheckConstraint("transaction_type IN ('BUY', 'RENT')", name="ck_requirement_transaction"),
        CheckConstraint("budget_min IS NULL OR budget_min >= 0", name="ck_requirement_budget_min"),
        CheckConstraint("budget_max IS NULL OR budget_max >= 0", name="ck_requirement_budget_max"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    transaction_type: Mapped[str] = mapped_column(String(4), nullable=False)
    budget_min: Mapped[float | None] = mapped_column(Float)
    budget_max: Mapped[float | None] = mapped_column(Float)
    preferred_locations: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    property_type: Mapped[str | None] = mapped_column(String(80))
    bedrooms_min: Mapped[int | None] = mapped_column()
    area_min_sqm: Mapped[float | None] = mapped_column(Float)
    timeline: Mapped[str | None] = mapped_column(String(200))
    additional_requirements: Mapped[str | None] = mapped_column(Text)
    preferred_language: Mapped[str] = mapped_column(String(20), default="zh", nullable=False)
    contact_name: Mapped[str] = mapped_column(String(160), nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(254))
    contact_phone: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class Property(Base):
    __tablename__ = "properties"
    __table_args__ = (
        CheckConstraint("transaction_type IN ('BUY', 'RENT')", name="ck_property_transaction"),
        CheckConstraint("data_label IN ('DEMO', 'REAL')", name="ck_property_data_label"),
        CheckConstraint("status IN ('AVAILABLE', 'UNAVAILABLE', 'CLOSED')", name="ck_property_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    transaction_type: Mapped[str] = mapped_column(String(4), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str] = mapped_column(String(160), nullable=False)
    neighborhood: Mapped[str | None] = mapped_column(String(160))
    price: Mapped[float] = mapped_column(Float, nullable=False)
    area_sqm: Mapped[float] = mapped_column(Float, nullable=False)
    bedrooms: Mapped[int | None] = mapped_column()
    bathrooms: Mapped[int | None] = mapped_column()
    property_type: Mapped[str] = mapped_column(String(80), nullable=False)
    condition: Mapped[str | None] = mapped_column(String(80))
    floor: Mapped[str | None] = mapped_column(String(40))
    has_elevator: Mapped[bool | None] = mapped_column(Boolean)
    images: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    source: Mapped[str | None] = mapped_column(String(200))
    data_label: Mapped[str] = mapped_column(String(5), default="DEMO", nullable=False)
    status: Mapped[str] = mapped_column(String(12), default="AVAILABLE", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    profile_type: Mapped[str] = mapped_column(String(12), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    agency_name: Mapped[str | None] = mapped_column(String(160))
    service_areas: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    specializations: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    languages: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(254))
    contact_phone: Mapped[str | None] = mapped_column(String(40))
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (CheckConstraint(
        "status IN ('NEW', 'REVIEWING', 'MATCHED', 'CONTACTED', "
        "'VIEWING_SCHEDULED', 'CONVERTED', 'CLOSED')",
        name="ck_lead_status",
    ),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    requirement_id: Mapped[str] = mapped_column(
        ForeignKey("customer_requirements.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    assigned_agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"))
    status: Mapped[str] = mapped_column(String(24), default="NEW", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class LeadNote(Base):
    __tablename__ = "lead_notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class LeadEvent(Base):
    __tablename__ = "lead_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    details: Mapped[dict[str, str | None]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ViewingRequest(Base):
    __tablename__ = "viewing_requests"
    __table_args__ = (CheckConstraint(
        "status IN ('NEW', 'SCHEDULED', 'COMPLETED', 'CANCELLED')",
        name="ck_viewing_status",
    ),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    requirement_id: Mapped[str] = mapped_column(
        ForeignKey("customer_requirements.id", ondelete="CASCADE"), nullable=False
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("properties.id"), nullable=False)
    assigned_agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"))
    preferred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    customer_notes: Mapped[str | None] = mapped_column(Text)
    report_references: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(12), default="NEW", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
