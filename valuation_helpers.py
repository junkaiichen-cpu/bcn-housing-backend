RENTAL_TYPE_LABELS = {
    "entire": {"label_zh": "整套公寓", "label_en": "Entire apartment"},
    "studio": {"label_zh": "Studio", "label_en": "Studio"},
    "private_room": {"label_zh": "独立卧室", "label_en": "Private room"},
    "shared_room": {"label_zh": "共享卧室", "label_en": "Shared room"},
    # Backward compatibility for the original UI/API.
    "room": {"label_zh": "独立卧室", "label_en": "Private room"},
}

FLOOR_LABELS = {
    "Middle": "中间楼层",
    "Ático": "顶楼 / 阁楼",
    "Bajo": "底层",
    "顶楼": "顶楼 / 阁楼",
    "底层": "底层",
}

CONDITION_LABELS = {
    "good": "良好",
    "renovated": "已翻新",
    "needs_renovation": "需要翻修",
}

CONTRACT_TYPE_LABELS = {
    "LAU_LONG_TERM": "长期住宅合同",
    "TEMPORADA": "季节性 / 临时租赁合同",
    "ROOM": "合租房间合同",
}


def normalize_rental_type(value: str):
    return RENTAL_TYPE_LABELS.get(value, {"label_zh": value or "未指定", "label_en": value or "Unspecified"})


def _assessment(difference_percent: float):
    if difference_percent <= -10:
        return "below_expected"
    if difference_percent < -3:
        return "within_or_below"
    if difference_percent <= 3:
        return "within_expected"
    if difference_percent <= 10:
        return "above_expected"
    return "well_above_expected"


def compare_user_price(user_price, estimated_monthly_rent, estimated_min, estimated_max):
    if user_price is None or float(user_price) <= 0:
        return {
            "provided": False,
            "period": "monthly",
            "amount": None,
            "difference_percent": None,
            "assessment": "not_provided",
        }

    amount = float(user_price)
    difference_percent = round((amount - estimated_monthly_rent) / estimated_monthly_rent * 100, 2)
    assessment = _assessment(difference_percent)
    if estimated_min <= amount <= estimated_max:
        assessment = "within_expected"

    return {
        "provided": True,
        "period": "monthly",
        "amount": round(amount, 2),
        "difference_percent": difference_percent,
        "assessment": assessment,
        "estimated_range": {"min": estimated_min, "max": estimated_max},
    }


def build_valuation_benchmark(
    *, estimated_monthly_rent, estimated_min, estimated_max, area_sqm,
    avg_rent_sqm, loc, rental_type, floor_level, has_elevator, condition,
    contract_type,
):
    monthly_per_sqm_min = estimated_min / area_sqm if area_sqm else 0
    monthly_per_sqm_max = estimated_max / area_sqm if area_sqm else 0
    rental = normalize_rental_type(rental_type)
    return {
        "estimated_rent": {"label": "预测月租", "value": f"€{estimated_min:,.0f}–€{estimated_max:,.0f} / 月"},
        "price_per_sqm": {"label": "预测单价", "value": f"€{monthly_per_sqm_min:,.1f}–€{monthly_per_sqm_max:,.1f} / m² / 月"},
        "area": {"label": "面积", "value": f"{area_sqm:g} m²"},
        "location": {"label": "区域", "value": f"{loc['municipio']} · {loc['barrio']}"},
        "property_type": {"label": "房源类型", "value": rental["label_zh"]},
        "floor": {"label": "楼层", "value": FLOOR_LABELS.get(floor_level, floor_level or "未指定")},
        "elevator": {"label": "电梯", "value": "有" if has_elevator else "无"},
        "condition": {"label": "房屋状况", "value": CONDITION_LABELS.get(condition, condition or "未指定")},
        "contract_type": {"label": "合同类型", "value": CONTRACT_TYPE_LABELS.get(contract_type, contract_type or "未指定")},
        "market_rent_sqm": {"label": "区域租金基准", "value": f"€{avg_rent_sqm:g} / m² / 月"},
    }
