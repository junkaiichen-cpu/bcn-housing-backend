from sqlalchemy import select
from sqlalchemy.orm import Session

from bcn_housing.models import Property


DEMO_PROPERTIES = [
    {
        "transaction_type": "RENT",
        "title": "[DEMO] Example two-bedroom apartment",
        "description": "Illustrative demo record only; not a real listing.",
        "location": "Barcelona",
        "neighborhood": "Eixample",
        "price": 1800,
        "area_sqm": 75,
        "bedrooms": 2,
        "bathrooms": 1,
        "property_type": "apartment",
        "condition": "good",
        "has_elevator": True,
        "source": "DEMO ONLY",
        "data_label": "DEMO",
    },
    {
        "transaction_type": "RENT",
        "title": "[DEMO] Example one-bedroom apartment",
        "description": "Illustrative demo record only; not a real listing.",
        "location": "Barcelona",
        "neighborhood": "Sants",
        "price": 1250,
        "area_sqm": 52,
        "bedrooms": 1,
        "bathrooms": 1,
        "property_type": "apartment",
        "condition": "renovated",
        "has_elevator": True,
        "source": "DEMO ONLY",
        "data_label": "DEMO",
    },
    {
        "transaction_type": "BUY",
        "title": "[DEMO] Example family apartment for purchase",
        "description": "Illustrative demo record only; not a real listing.",
        "location": "Barcelona",
        "neighborhood": "Sant Andreu",
        "price": 295000,
        "area_sqm": 88,
        "bedrooms": 3,
        "bathrooms": 2,
        "property_type": "apartment",
        "condition": "good",
        "has_elevator": True,
        "source": "DEMO ONLY",
        "data_label": "DEMO",
    },
]


def seed_demo_properties(db: Session) -> None:
    if db.scalar(select(Property.id).limit(1)) is None:
        db.add_all(Property(**item) for item in DEMO_PROPERTIES)
        db.commit()
