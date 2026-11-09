import os

from bcn_housing.models import CustomerRequirement, Property


def _weight(name: str, default: int) -> int:
    try:
        value = int(os.getenv(f"MATCH_WEIGHT_{name.upper()}", str(default)))
    except ValueError as exc:
        raise RuntimeError(f"MATCH_WEIGHT_{name.upper()} must be an integer") from exc
    if value < 0:
        raise RuntimeError(f"MATCH_WEIGHT_{name.upper()} cannot be negative")
    return value


WEIGHTS = {
    "budget": _weight("budget", 35),
    "location": _weight("location", 25),
    "property_type": _weight("property_type", 15),
    "bedrooms": _weight("bedrooms", 15),
    "area": _weight("area", 10),
}
if not any(WEIGHTS.values()):
    raise RuntimeError("At least one match weight must be greater than zero")


def match_property(requirement: CustomerRequirement, property_record: Property) -> dict:
    explanations: list[str] = []
    incompatible: list[str] = []
    missing: list[str] = []
    earned = 0.0
    possible = 0

    if requirement.transaction_type != property_record.transaction_type:
        incompatible.append("Transaction type does not match")
    else:
        explanations.append(f"Transaction type matches ({requirement.transaction_type})")

    if requirement.budget_min is not None or requirement.budget_max is not None:
        possible += WEIGHTS["budget"]
        if requirement.budget_max is not None and property_record.price > requirement.budget_max:
            incompatible.append("Property price exceeds the maximum budget")
        elif requirement.budget_min is not None and property_record.price < requirement.budget_min:
            earned += WEIGHTS["budget"] * 0.5
            explanations.append("Price is below the requested budget range but remains affordable")
        else:
            earned += WEIGHTS["budget"]
            explanations.append("Price is within the stated budget")
    else:
        missing.append("Budget was not provided")

    if requirement.preferred_locations:
        possible += WEIGHTS["location"]
        searchable_location = f"{property_record.location} {property_record.neighborhood or ''}".casefold()
        if any(location.casefold() in searchable_location for location in requirement.preferred_locations):
            earned += WEIGHTS["location"]
            explanations.append("Property is in a preferred location")
        else:
            incompatible.append("Property is outside the preferred locations")
    else:
        missing.append("Preferred locations were not provided")

    if requirement.property_type:
        possible += WEIGHTS["property_type"]
        if requirement.property_type.casefold() == property_record.property_type.casefold():
            earned += WEIGHTS["property_type"]
            explanations.append("Property type matches")
        else:
            incompatible.append("Property type does not match")
    else:
        missing.append("Property type preference was not provided")

    if requirement.bedrooms_min is not None:
        possible += WEIGHTS["bedrooms"]
        if property_record.bedrooms is None:
            missing.append("Property bedroom count is unavailable")
        elif property_record.bedrooms >= requirement.bedrooms_min:
            earned += WEIGHTS["bedrooms"]
            explanations.append("Bedroom count meets the minimum")
        else:
            incompatible.append("Property has fewer bedrooms than requested")
    else:
        missing.append("Minimum bedroom count was not provided")

    if requirement.area_min_sqm is not None:
        possible += WEIGHTS["area"]
        if property_record.area_sqm >= requirement.area_min_sqm:
            earned += WEIGHTS["area"]
            explanations.append("Property area meets the minimum")
        else:
            incompatible.append("Property area is below the requested minimum")
    else:
        missing.append("Minimum area was not provided")

    if requirement.additional_requirements:
        missing.append("Additional free-text requirements need manual review")

    score = round(earned / possible * 100, 1) if possible else 0.0
    return {
        "property_id": property_record.id,
        "match_score": score,
        "is_match": not incompatible,
        "explanations": explanations,
        "incompatible_requirements": incompatible,
        "missing_or_unverified": missing,
        "score_is_not_a_guarantee": True,
    }
