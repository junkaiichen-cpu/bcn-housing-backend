"""BCN Housing backend compatibility bootstrap.

The legacy engine/data set is loaded from the last stable commit, while the
valuation endpoint is replaced with a clearer contract for optional pricing,
multiple rental types and benchmark output. This keeps the large regional
catalog intact while allowing the API contract to evolve safely.
"""
import json
import os
import urllib.request
from typing import Optional, Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Use the reachable commit that contains the original regional engine.
# The previous value was a Git blob SHA, not a commit/ref, so Render could not
# download it and the service failed during module import.
LEGACY_COMMIT = "d6a31023e6c870280c9d39298143f55435ff3ccf"
LEGACY_URL = f"https://raw.githubusercontent.com/junkaiichen-cpu/bcn-housing-backend/{LEGACY_COMMIT}/main.py"


def _load_legacy_engine():
    try:
        with urllib.request.urlopen(LEGACY_URL, timeout=15) as response:
            source = response.read().decode("utf-8")
    except Exception as exc:
        raise RuntimeError(f"Unable to load the stable regional engine: {exc}") from exc
    namespace: Dict[str, Any] = {"__name__": "legacy_engine"}
    exec(compile(source, LEGACY_URL, "exec"), namespace, namespace)
    return namespace


legacy = _load_legacy_engine()
app: FastAPI = legacy["app"]
resolve_location_data = legacy["resolve_location_data"]
call_groq_llm = legacy["call_groq_llm"]

from valuation_helpers import (  # noqa: E402
    CONTRACT_TYPE_LABELS,
    CONDITION_LABELS,
    FLOOR_LABELS,
    build_valuation_benchmark,
    compare_user_price,
    normalize_rental_type,
)


class PropertyEvaluationRequestV2(BaseModel):
    intent: str = Field("rent")
    rental_type: str = Field("entire")
    comarca: str = Field("Barcelonès")
    municipio: str = Field("Barcelona")
    barrio: Optional[str] = None
    address: Optional[str] = None
    price: Optional[float] = Field(None, ge=0)
    price_mode: str = Field("monthly", description="monthly or total")
    term_months: Optional[int] = Field(12, ge=1)
    area_sqm: Optional[float] = Field(None, gt=0)
    bedrooms: Optional[int] = Field(1, ge=0)
    floor_level: Optional[str] = "Middle"
    has_elevator: Optional[bool] = True
    condition: Optional[str] = "good"
    contract_type: Optional[str] = "LAU_LONG_TERM"
    description: Optional[str] = None


def _remove_legacy_evaluation_routes():
    paths = {"/api/evaluate", "/api/evaluate-property"}
    app.router.routes[:] = [route for route in app.router.routes if getattr(route, "path", None) not in paths]


def _rental_factor(rental_type: str) -> float:
    return {"entire": 1.0, "studio": 1.04, "private_room": 1.15, "shared_room": 0.90, "room": 1.15}.get(rental_type, 1.0)


def _assessment_text(difference_percent: Optional[float], provided: bool) -> str:
    if not provided:
        return "未提供报价，以下为基于房源参数的合理价格预测。"
    if difference_percent is None:
        return "已提供报价，但暂时无法完成偏差计算。"
    if difference_percent <= -10:
        return f"报价低于模型预测中位数约 {abs(difference_percent):.1f}%，价格具有吸引力。"
    if difference_percent < -3:
        return f"报价略低于模型预测中位数约 {abs(difference_percent):.1f}%，整体偏合理。"
    if difference_percent <= 3:
        return "报价接近模型预测中位数，价格整体合理。"
    if difference_percent <= 10:
        return f"报价高于模型预测中位数约 {difference_percent:.1f}%，建议进一步核实房屋条件和费用包含范围。"
    return f"报价明显高于模型预测中位数约 {difference_percent:.1f}%，建议谨慎并尝试议价。"


def _remove_and_register_evaluation():
    _remove_legacy_evaluation_routes()

    @app.post("/api/evaluate")
    @app.post("/api/evaluate-property")
    async def evaluate_property_v2(req: PropertyEvaluationRequestV2):
        try:
            loc = resolve_location_data(req.comarca, req.municipio, req.barrio)
            default_sqm = 20.0 if req.rental_type in {"private_room", "shared_room", "room"} else {1: 45.0, 2: 65.0, 3: 85.0}.get(req.bedrooms or 1, 60.0)
            sqm = req.area_sqm or default_sqm
            adj_factor = loc["barrio_adj"] * _rental_factor(req.rental_type)
            if req.condition == "renovated": adj_factor += 0.08
            elif req.condition == "needs_renovation": adj_factor -= 0.12
            if req.floor_level in {"Ático", "顶楼"}: adj_factor += 0.07
            elif req.floor_level in {"Bajo", "底层"} and not req.has_elevator: adj_factor -= 0.10
            if not req.has_elevator and sqm > 40: adj_factor -= 0.08
            adj_factor = max(adj_factor, 0.5)

            if req.intent == "buy":
                fair_value = round(loc["avg_sale_sqm"] * sqm * adj_factor, 2)
                user_price = req.price if req.price and req.price > 0 else None
                difference = round((user_price - fair_value) / fair_value * 100, 2) if user_price else None
                metrics = {
                    "transaction_mode": "房屋买卖",
                    "location": f"{loc['municipio']} · {loc['barrio']}",
                    "area": f"{sqm:g} m²",
                    "official_avg_sale_sqm": f"€{loc['avg_sale_sqm']:g} / m²",
                    "adjusted_fair_value": f"€{fair_value:,.0f}",
                    "variance_pct": f"{difference:.1f}%" if difference is not None else "未提供报价",
                    "expected_gross_yield": f"{loc['gross_yield']}%",
                }
                benchmark = {k: {"label": k.replace("_", " "), "value": v} for k, v in metrics.items()}
                price_assessment = compare_user_price(user_price, fair_value, fair_value * 0.95, fair_value * 1.05)
            else:
                predicted = round(loc["avg_rent_sqm"] * sqm * adj_factor, 2)
                estimated_min = round(predicted * 0.95, 2)
                estimated_max = round(predicted * 1.05, 2)
                if req.price and req.price > 0:
                    monthly_user_price = req.price / (req.term_months or 12) if req.price_mode == "total" else req.price
                else:
                    monthly_user_price = None
                price_assessment = compare_user_price(monthly_user_price, predicted, estimated_min, estimated_max)
                benchmark = build_valuation_benchmark(
                    estimated_monthly_rent=predicted,
                    estimated_min=estimated_min,
                    estimated_max=estimated_max,
                    area_sqm=sqm,
                    avg_rent_sqm=loc["avg_rent_sqm"],
                    loc=loc,
                    rental_type=req.rental_type,
                    floor_level=req.floor_level or "Middle",
                    has_elevator=bool(req.has_elevator),
                    condition=req.condition or "good",
                    contract_type=req.contract_type or "LAU_LONG_TERM",
                )
                benchmark["zone_status"] = {"label": "价格管制区域", "value": "紧张住房区" if loc["zone_tensionada"] else "自由市场区域"}
                benchmark["bedrooms"] = {"label": "卧室", "value": str(req.bedrooms or 0)}
                metrics = {k: v["value"] for k, v in benchmark.items()}
                fair_value = predicted
                difference = price_assessment["difference_percent"]

            rating = "价格合理" if difference is None or abs(difference) <= 5 else ("偏贵溢价" if difference > 5 else "价格有吸引力")
            summary = {
                "rating": rating,
                "adjusted_fair_value": f"€{fair_value:,.0f}" + (" / 月" if req.intent == "rent" else ""),
                "variance_percentage": f"{difference:.1f}%" if difference is not None else "未提供报价",
                "value_verdict": _assessment_text(difference, price_assessment["provided"]),
            }

            ai_analysis = {
                "comarca_positioning": loc["comarca_desc"],
                "municipio_and_barrio_insight": f"{loc['municipio']} · {loc['barrio']}；治安 {loc['safety_score']}/10，宜居度 {loc['livability_score']}/10。",
            }
            financial = _assessment_text(difference, price_assessment["provided"])
            advice = [
                "核实报价是否包含水电、物业、网络及其他附加费用。",
                "若报价高于预测区间，重点核实装修、电梯、采光、家具及合同条件是否能解释溢价。",
            ]

            if os.getenv("GROQ_API_KEY"):
                try:
                    prompt = f"""请用简洁中文分析这套巴塞罗那房源。不要改变任何数字，只解释价格合理性、区域特点和两条行动建议。房源指标：{json.dumps(metrics, ensure_ascii=False)}"""
                    llm = call_groq_llm(prompt, "你是巴塞罗那房地产分析师。只返回 JSON，字段为 geographic_summary、financial_summary、advice。")
                    ai_analysis["llm"] = llm
                    financial = llm.get("financial_summary", financial) if isinstance(llm, dict) else financial
                    advice = llm.get("advice", advice) if isinstance(llm, dict) and isinstance(llm.get("advice"), list) else advice
                except Exception:
                    pass

            return {"status": "success", "data": {
                "valuation_summary": summary,
                "valuation": {"estimated_monthly_rent": fair_value if req.intent == "rent" else None, "estimated_min": estimated_min if req.intent == "rent" else None, "estimated_max": estimated_max if req.intent == "rent" else None},
                "user_price": price_assessment,
                "property": {"type": normalize_rental_type(req.rental_type), "area_sqm": sqm, "bedrooms": req.bedrooms, "floor": FLOOR_LABELS.get(req.floor_level or "Middle", req.floor_level), "elevator": bool(req.has_elevator), "condition": CONDITION_LABELS.get(req.condition or "good", req.condition)},
                "contract": {"type": req.contract_type, "label": CONTRACT_TYPE_LABELS.get(req.contract_type or "", req.contract_type or "未指定")},
                "geographic_and_location_analysis": ai_analysis,
                "financial_and_yield_breakdown": financial,
                "actionable_negotiation_strategy": advice,
                "valuation_benchmark": benchmark,
                "compliance_status": "紧张住房区" if loc["zone_tensionada"] else "自由市场区域",
                "risk_analysis": {"zone_tensionada": loc["zone_tensionada"]},
            }}
        except Exception as exc:
            return JSONResponse(status_code=500, content={"status": "error", "message": str(exc)})


_remove_and_register_evaluation()

# Keep the legacy geography, regional comparison and rental-risk endpoints intact.
