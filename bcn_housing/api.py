import threading
import time
from collections import defaultdict, deque
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from bcn_housing.database import get_db
from bcn_housing.matching import match_property
from bcn_housing.models import (
    Agent,
    CustomerRequirement,
    Lead,
    LeadEvent,
    LeadNote,
    Property,
    ViewingRequest,
)
from bcn_housing.schemas import (
    AdminLogin,
    AgentAssignment,
    AgentCreate,
    AgentStatusUpdate,
    LeadNoteCreate,
    LeadStatusUpdate,
    PropertyCreate,
    PropertyStatusUpdate,
    RequirementCreate,
    ViewingCreate,
    ViewingUpdate,
)
from bcn_housing.security import authenticate_admin, create_admin_token, require_admin


router = APIRouter(prefix="/api")
admin_router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])
_login_attempts: dict[str, deque[float]] = defaultdict(deque)
_login_attempts_lock = threading.Lock()
_LOGIN_LIMIT = 10
_LOGIN_WINDOW_SECONDS = 60


async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [
        {"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errors})


def _enforce_login_limit(client_key: str) -> None:
    now = time.monotonic()
    with _login_attempts_lock:
        attempts = _login_attempts[client_key]
        while attempts and now - attempts[0] >= _LOGIN_WINDOW_SECONDS:
            attempts.popleft()
        if len(attempts) >= _LOGIN_LIMIT:
            raise HTTPException(status_code=429, detail="Too many login attempts; try again later")
        attempts.append(now)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _property_response(item: Property) -> dict:
    return {
        "id": item.id,
        "transaction_type": item.transaction_type,
        "title": item.title,
        "description": item.description,
        "location": item.location,
        "neighborhood": item.neighborhood,
        "price": item.price,
        "area_sqm": item.area_sqm,
        "bedrooms": item.bedrooms,
        "bathrooms": item.bathrooms,
        "property_type": item.property_type,
        "condition": item.condition,
        "floor": item.floor,
        "has_elevator": item.has_elevator,
        "images": item.images,
        "source": item.source,
        "data_label": item.data_label,
        "status": item.status,
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
    }


def _requirement_admin_response(item: CustomerRequirement) -> dict:
    return {
        "id": item.id,
        "transaction_type": item.transaction_type,
        "budget_min": item.budget_min,
        "budget_max": item.budget_max,
        "preferred_locations": item.preferred_locations,
        "property_type": item.property_type,
        "bedrooms_min": item.bedrooms_min,
        "area_min_sqm": item.area_min_sqm,
        "timeline": item.timeline,
        "additional_requirements": item.additional_requirements,
        "preferred_language": item.preferred_language,
        "contact": {
            "name": item.contact_name,
            "email": item.contact_email,
            "phone": item.contact_phone,
        },
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
    }


def _lead_response(lead: Lead, requirement: CustomerRequirement, agent: Agent | None) -> dict:
    return {
        "id": lead.id,
        "status": lead.status,
        "requirement": _requirement_admin_response(requirement),
        "assigned_agent": (
            {"id": agent.id, "name": agent.name, "profile_type": agent.profile_type}
            if agent
            else None
        ),
        "created_at": _iso(lead.created_at),
        "updated_at": _iso(lead.updated_at),
    }


def _matching_results(db: Session, requirement: CustomerRequirement) -> dict:
    properties = db.scalars(
        select(Property).where(
            Property.status == "AVAILABLE",
            Property.transaction_type == requirement.transaction_type,
        )
    ).all()
    results = []
    excluded = []
    for item in properties:
        result = match_property(requirement, item)
        candidate = {**result, "property": _property_response(item)}
        (results if result["is_match"] else excluded).append(candidate)
    results.sort(key=lambda result: (-result["match_score"], result["property"]["id"]))
    excluded.sort(key=lambda result: (-result["match_score"], result["property"]["id"]))
    return {
        "requirement_id": requirement.id,
        "matches": results,
        "match_count": len(results),
        "excluded_properties": excluded,
        "message": None if results else "No available properties currently match these requirements",
        "method": "deterministic_rules",
    }


def _get_requirement(db: Session, requirement_id: str) -> CustomerRequirement:
    item = db.get(CustomerRequirement, requirement_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Requirement not found")
    return item


def _get_lead_with_requirement(db: Session, lead_id: str) -> tuple[Lead, CustomerRequirement]:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    requirement = _get_requirement(db, lead.requirement_id)
    return lead, requirement


@router.post("/requirements", status_code=status.HTTP_201_CREATED)
def submit_requirement(payload: RequirementCreate, db: Session = Depends(get_db)) -> dict:
    requirement = CustomerRequirement(**payload.model_dump())
    db.add(requirement)
    db.flush()
    lead = Lead(requirement_id=requirement.id)
    db.add(lead)
    db.commit()
    db.refresh(requirement)
    return {
        "id": requirement.id,
        "lead_id": lead.id,
        "transaction_type": requirement.transaction_type,
        "created_at": _iso(requirement.created_at),
        "message": "Requirement received",
    }


@router.get("/requirements/{requirement_id}/matches")
def get_matches(requirement_id: str, db: Session = Depends(get_db)) -> dict:
    return _matching_results(db, _get_requirement(db, requirement_id))


@router.get("/properties")
def list_public_properties(
    transaction_type: str | None = None, db: Session = Depends(get_db)
) -> dict:
    query = select(Property).where(Property.status == "AVAILABLE")
    if transaction_type is not None:
        if transaction_type not in {"BUY", "RENT"}:
            raise HTTPException(status_code=422, detail="transaction_type must be BUY or RENT")
        query = query.where(Property.transaction_type == transaction_type)
    properties = db.scalars(query.order_by(Property.created_at.desc())).all()
    return {"properties": [_property_response(item) for item in properties]}


@router.get("/properties/{property_id}")
def get_public_property(property_id: str, db: Session = Depends(get_db)) -> dict:
    item = db.get(Property, property_id)
    if item is None or item.status != "AVAILABLE":
        raise HTTPException(status_code=404, detail="Property not found")
    return _property_response(item)


@router.post("/viewing-requests", status_code=status.HTTP_201_CREATED)
def submit_viewing_request(payload: ViewingCreate, db: Session = Depends(get_db)) -> dict:
    requirement = _get_requirement(db, payload.requirement_id)
    property_record = db.get(Property, payload.property_id)
    if property_record is None or property_record.status != "AVAILABLE":
        raise HTTPException(status_code=404, detail="Available property not found")
    result = match_property(requirement, property_record)
    if not result["is_match"]:
        raise HTTPException(status_code=422, detail="Property does not match this requirement")
    request = ViewingRequest(**payload.model_dump())
    db.add(request)
    db.flush()
    lead = db.scalar(select(Lead).where(Lead.requirement_id == requirement.id))
    if lead is not None:
        db.add(LeadEvent(lead_id=lead.id, event_type="VIEWING_REQUESTED", details={"viewing_request_id": request.id}))
    db.commit()
    db.refresh(request)
    return {
        "id": request.id,
        "status": request.status,
        "created_at": _iso(request.created_at),
        "message": "Viewing request received",
    }


@router.post("/admin/login")
def admin_login(payload: AdminLogin, request: Request) -> dict:
    _enforce_login_limit(request.client.host if request.client else "unknown")
    if not authenticate_admin(payload.username, payload.password):
        raise HTTPException(status_code=401, detail="Invalid administrator credentials")
    token = create_admin_token(payload.username)
    return {"access_token": token, "token_type": "bearer", "expires_in": 8 * 60 * 60}


@admin_router.post("/properties", status_code=status.HTTP_201_CREATED)
def create_property(payload: PropertyCreate, db: Session = Depends(get_db)) -> dict:
    item = Property(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return _property_response(item)


@admin_router.get("/properties")
def list_admin_properties(db: Session = Depends(get_db)) -> dict:
    items = db.scalars(select(Property).order_by(Property.created_at.desc())).all()
    return {"properties": [_property_response(item) for item in items]}


@admin_router.patch("/properties/{property_id}/status")
def update_property_status(
    property_id: str, payload: PropertyStatusUpdate, db: Session = Depends(get_db)
) -> dict:
    item = db.get(Property, property_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Property not found")
    item.status = payload.status
    db.commit()
    return {"id": item.id, "status": item.status, "updated_at": _iso(item.updated_at)}


@admin_router.post("/agents", status_code=status.HTTP_201_CREATED)
def create_agent(payload: AgentCreate, db: Session = Depends(get_db)) -> dict:
    item = Agent(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return {
        "id": item.id,
        "profile_type": item.profile_type,
        "name": item.name,
        "active": item.active,
        "created_at": _iso(item.created_at),
    }


@admin_router.patch("/agents/{agent_id}/status")
def update_agent_status(
    agent_id: str, payload: AgentStatusUpdate, db: Session = Depends(get_db)
) -> dict:
    item = db.get(Agent, agent_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    item.active = payload.active
    if payload.verified is not None:
        item.verified = payload.verified
    db.commit()
    return {"id": item.id, "active": item.active, "verified": item.verified, "updated_at": _iso(item.updated_at)}


@admin_router.get("/agents")
def list_agents(db: Session = Depends(get_db)) -> dict:
    items = db.scalars(select(Agent).order_by(Agent.name)).all()
    return {
        "agents": [
            {
                "id": item.id,
                "profile_type": item.profile_type,
                "name": item.name,
                "agency_name": item.agency_name,
                "service_areas": item.service_areas,
                "specializations": item.specializations,
                "languages": item.languages,
                "contact_email": item.contact_email,
                "contact_phone": item.contact_phone,
                "verified": item.verified,
                "active": item.active,
                "created_at": _iso(item.created_at),
            }
            for item in items
        ]
    }


@admin_router.get("/leads")
def list_leads(
    status_filter: str | None = None, db: Session = Depends(get_db)
) -> dict:
    query = select(Lead, CustomerRequirement).join(
        CustomerRequirement, Lead.requirement_id == CustomerRequirement.id
    )
    if status_filter is not None:
        allowed = {"NEW", "REVIEWING", "MATCHED", "CONTACTED", "VIEWING_SCHEDULED", "CONVERTED", "CLOSED"}
        if status_filter not in allowed:
            raise HTTPException(status_code=422, detail="Unknown lead status")
        query = query.where(Lead.status == status_filter)
    rows = db.execute(query.order_by(Lead.created_at.desc())).all()
    return {
        "leads": [
            _lead_response(lead, requirement, db.get(Agent, lead.assigned_agent_id) if lead.assigned_agent_id else None)
            for lead, requirement in rows
        ]
    }


@admin_router.get("/leads/{lead_id}")
def get_lead(lead_id: str, db: Session = Depends(get_db)) -> dict:
    lead, requirement = _get_lead_with_requirement(db, lead_id)
    agent = db.get(Agent, lead.assigned_agent_id) if lead.assigned_agent_id else None
    notes = db.scalars(select(LeadNote).where(LeadNote.lead_id == lead.id).order_by(LeadNote.created_at)).all()
    events = db.scalars(select(LeadEvent).where(LeadEvent.lead_id == lead.id).order_by(LeadEvent.created_at)).all()
    return {
        **_lead_response(lead, requirement, agent),
        "matching_results": _matching_results(db, requirement),
        "notes": [{"id": note.id, "note": note.note, "created_at": _iso(note.created_at)} for note in notes],
        "history": [
            {"event_type": event.event_type, "details": event.details, "created_at": _iso(event.created_at)}
            for event in events
        ],
    }


@admin_router.get("/leads/{lead_id}/matches")
def get_admin_matches(lead_id: str, db: Session = Depends(get_db)) -> dict:
    _, requirement = _get_lead_with_requirement(db, lead_id)
    return _matching_results(db, requirement)


@admin_router.put("/leads/{lead_id}/agent")
def assign_agent(lead_id: str, payload: AgentAssignment, db: Session = Depends(get_db)) -> dict:
    lead, _ = _get_lead_with_requirement(db, lead_id)
    agent = db.get(Agent, payload.agent_id)
    if agent is None or not agent.active:
        raise HTTPException(status_code=404, detail="Active agent not found")
    previous_id = lead.assigned_agent_id
    lead.assigned_agent_id = agent.id
    db.add(LeadEvent(
        lead_id=lead.id,
        event_type="AGENT_ASSIGNED",
        details={"previous_agent_id": previous_id, "agent_id": agent.id},
    ))
    db.commit()
    return {"lead_id": lead.id, "assigned_agent_id": agent.id, "updated_at": _iso(lead.updated_at)}


@admin_router.patch("/leads/{lead_id}/status")
def update_lead_status(lead_id: str, payload: LeadStatusUpdate, db: Session = Depends(get_db)) -> dict:
    lead, _ = _get_lead_with_requirement(db, lead_id)
    previous_status = lead.status
    lead.status = payload.status
    db.add(LeadEvent(
        lead_id=lead.id,
        event_type="STATUS_CHANGED",
        details={"previous_status": previous_status, "status": payload.status},
    ))
    db.commit()
    return {"lead_id": lead.id, "status": lead.status, "updated_at": _iso(lead.updated_at)}


@admin_router.post("/leads/{lead_id}/notes", status_code=status.HTTP_201_CREATED)
def add_lead_note(lead_id: str, payload: LeadNoteCreate, db: Session = Depends(get_db)) -> dict:
    lead, _ = _get_lead_with_requirement(db, lead_id)
    note = LeadNote(lead_id=lead.id, note=payload.note.strip())
    db.add(note)
    db.add(LeadEvent(lead_id=lead.id, event_type="NOTE_ADDED", details={}))
    db.commit()
    db.refresh(note)
    return {"id": note.id, "created_at": _iso(note.created_at)}


@admin_router.delete("/leads/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lead(lead_id: str, db: Session = Depends(get_db)) -> None:
    lead, requirement = _get_lead_with_requirement(db, lead_id)
    viewing_ids = select(ViewingRequest.id).where(ViewingRequest.requirement_id == requirement.id)
    db.execute(delete(ViewingRequest).where(ViewingRequest.id.in_(viewing_ids)))
    db.execute(delete(LeadNote).where(LeadNote.lead_id == lead.id))
    db.execute(delete(LeadEvent).where(LeadEvent.lead_id == lead.id))
    db.delete(lead)
    db.delete(requirement)
    db.commit()


@admin_router.get("/viewing-requests")
def list_viewing_requests(db: Session = Depends(get_db)) -> dict:
    requests = db.scalars(select(ViewingRequest).order_by(ViewingRequest.created_at.desc())).all()
    return {
        "viewing_requests": [
            {
                "id": item.id,
                "requirement_id": item.requirement_id,
                "property": _property_response(db.get(Property, item.property_id)),
                "customer": {
                    "name": db.get(CustomerRequirement, item.requirement_id).contact_name,
                    "email": db.get(CustomerRequirement, item.requirement_id).contact_email,
                    "phone": db.get(CustomerRequirement, item.requirement_id).contact_phone,
                },
                "assigned_agent_id": item.assigned_agent_id,
                "preferred_at": _iso(item.preferred_at),
                "customer_notes": item.customer_notes,
                "report_references": item.report_references,
                "status": item.status,
                "created_at": _iso(item.created_at),
                "updated_at": _iso(item.updated_at),
            }
            for item in requests
        ]
    }


@admin_router.patch("/viewing-requests/{request_id}")
def update_viewing_request(request_id: str, payload: ViewingUpdate, db: Session = Depends(get_db)) -> dict:
    item = db.get(ViewingRequest, request_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Viewing request not found")
    if "assigned_agent_id" in payload.model_fields_set:
        if payload.assigned_agent_id is None:
            item.assigned_agent_id = None
        else:
            agent = db.get(Agent, payload.assigned_agent_id)
            if agent is None or not agent.active:
                raise HTTPException(status_code=404, detail="Active agent not found")
            item.assigned_agent_id = agent.id
    item.status = payload.status
    if "preferred_at" in payload.model_fields_set:
        item.preferred_at = payload.preferred_at
    if "report_references" in payload.model_fields_set:
        item.report_references = payload.report_references
    db.commit()
    lead = db.scalar(select(Lead).where(Lead.requirement_id == item.requirement_id))
    if lead is not None:
        db.add(LeadEvent(
            lead_id=lead.id,
            event_type="VIEWING_UPDATED",
            details={"viewing_request_id": item.id, "status": item.status},
        ))
        db.commit()
    return {"id": item.id, "status": item.status, "updated_at": _iso(item.updated_at)}


router.include_router(admin_router)
