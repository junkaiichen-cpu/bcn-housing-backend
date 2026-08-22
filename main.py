import sys
import os

# 清理代理设置，确保 API 请求畅通
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)

import json
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

app = FastAPI(
    title="Barcelona Real Estate Intelligence & Risk Engine",
    description="专为巴塞罗那全域打造的权威房产多维估值、全套街区匹配、租务风控与投资精算系统",
    version="6.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 优先读取环境变量，若无则使用兜底 Key
RAW_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_API_KEY = RAW_KEY.encode('ascii', 'ignore').decode('ascii').strip()

# 最新的 Groq 模型候选列表（从高优先到低优先）
# Groq 最新官方推荐稳定模型列表
MODEL_CANDIDATES = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant"
]

BCN_DATABASE: Dict[str, Dict[str, Any]] = {
    "Eixample": {
        "sub_barrios": ["Eixample Esquerra", "Eixample Dreta", "Sant Antoni", "Sagrada Família", "Fort Pienc"],
        "avg_rent_sqm": 19.5, "index_ref_sqm": 15.6, "avg_sale_sqm": 5100,
        "gross_yield": 4.6, "ibi_yearly_sqm": 7.5, "community_monthly": 85.0,
        "safety_score": 8.9, "livability_score": 9.3, "zone_tensionada": True,
        "pros": ["八角形经典街区，采光便利", "商业与生活配套全城最成熟", "房产流动性与保值率第一"],
        "cons": ["主干道车流噪音较大", "停车位极度紧缺"]
    },
    "Gràcia": {
        "sub_barrios": ["Vila de Gràcia", "Camp d'en Grassot", "Vallcarca", "El Coll", "La Salut"],
        "avg_rent_sqm": 19.8, "index_ref_sqm": 16.2, "avg_sale_sqm": 4750,
        "gross_yield": 5.0, "ibi_yearly_sqm": 6.8, "community_monthly": 55.0,
        "safety_score": 9.1, "livability_score": 9.0, "zone_tensionada": True,
        "pros": ["步行街步行体验极佳，文化小资氛围浓厚", "独立小店与 Plaza 广场密集"],
        "cons": ["老楼居多，普遍无电梯", "隔音一般且部分街道较窄"]
    },
    "Poblenou / Sant Martí": {
        "sub_barrios": ["El Poblenou", "Diagonal Mar", "El Besòs i el Maresme", "Provençals del Poblenou", "La Verneda"],
        "avg_rent_sqm": 19.0, "index_ref_sqm": 15.4, "avg_sale_sqm": 4600,
        "gross_yield": 4.9, "ibi_yearly_sqm": 8.0, "community_monthly": 95.0,
        "safety_score": 8.7, "livability_score": 9.2, "zone_tensionada": True,
        "pros": ["22@ 科技创新园区，现代公寓居多", "紧邻 Bogatell 与 Mar Bella 海滩"],
        "cons": ["部分工业转型街区夜间人流较少", "租金近年来涨幅较大"]
    },
    "Ciutat Vella / Gòtic": {
        "sub_barrios": ["El Gòtic", "El Raval", "El Born / Sant Pere", "La Barceloneta"],
        "avg_rent_sqm": 18.2, "index_ref_sqm": 14.9, "avg_sale_sqm": 4300,
        "gross_yield": 5.1, "ibi_yearly_sqm": 6.2, "community_monthly": 50.0,
        "safety_score": 5.8, "livability_score": 6.8, "zone_tensionada": True,
        "pros": ["巴塞罗那历史文化核心，出行极其便利", "老城独特建筑风情"],
        "cons": ["小偷与夜间喧闹风险较高", "老旧房屋潮湿且采光较差"]
    },
    "Les Corts / Pedralbes": {
        "sub_barrios": ["Les Corts", "Pedralbes", "Maternitat i Sant Ramon"],
        "avg_rent_sqm": 20.8, "index_ref_sqm": 17.2, "avg_sale_sqm": 6100,
        "gross_yield": 4.1, "ibi_yearly_sqm": 11.2, "community_monthly": 160.0,
        "safety_score": 9.6, "livability_score": 9.4, "zone_tensionada": True,
        "pros": ["顶尖豪宅区与大学城，治安极佳", "绿化率高，高品质社区"],
        "cons": ["租售门槛全城最高", "商业烟火气略逊于老城区"]
    },
    "Sants-Montjuïc": {
        "sub_barrios": ["Sants", "Poble Sec", "Hostafrancs", "La Bordeta", "Font de la Guatlla"],
        "avg_rent_sqm": 17.1, "index_ref_sqm": 14.3, "avg_sale_sqm": 3900,
        "gross_yield": 5.2, "ibi_yearly_sqm": 6.0, "community_monthly": 50.0,
        "safety_score": 8.1, "livability_score": 8.1, "zone_tensionada": True,
        "pros": ["Sants 交通枢纽，出行便利", "性价比高，生活配套齐全"],
        "cons": ["部分工人房楼龄偏老", "Poble Sec 夜间酒吧街稍吵"]
    },
    "Sarrià-Sant Gervasi": {
        "sub_barrios": ["Sarrià", "Sant Gervasi - Galvany", "El Putxet i el Farró", "Tres Torres", "Vallvidrera"],
        "avg_rent_sqm": 21.5, "index_ref_sqm": 18.0, "avg_sale_sqm": 5800,
        "gross_yield": 4.4, "ibi_yearly_sqm": 10.5, "community_monthly": 130.0,
        "safety_score": 9.7, "livability_score": 9.5, "zone_tensionada": True,
        "pros": ["传统富人区，极度安全安静", "顶级私立学校与医院集中"],
        "cons": ["坡道较多，出行依赖 FGC 或私家车", "日常消费偏高"]
    },
    "Sant Andreu / Sagrera": {
        "sub_barrios": ["Sant Andreu de Palomar", "La Sagrera", "Congrés i els Indians", "Navas"],
        "avg_rent_sqm": 15.0, "index_ref_sqm": 13.0, "avg_sale_sqm": 3300,
        "gross_yield": 5.4, "ibi_yearly_sqm": 5.8, "community_monthly": 45.0,
        "safety_score": 8.5, "livability_score": 8.0, "zone_tensionada": True,
        "pros": ["租金价格洼地，生活成本低", "La Sagrera 高铁枢纽升值潜力大"],
        "cons": ["距市中心需要 20 分钟以上地铁", "高质感精装房源相对较少"]
    },
    "Horta-Guinardó": {
        "sub_barrios": ["El Carmel", "Horta", "Guinardó", "Can Baró", "Montbau"],
        "avg_rent_sqm": 15.2, "index_ref_sqm": 13.2, "avg_sale_sqm": 3200,
        "gross_yield": 5.5, "ibi_yearly_sqm": 5.5, "community_monthly": 45.0,
        "safety_score": 8.3, "livability_score": 8.0, "zone_tensionada": True,
        "pros": ["山景公园多（Bunkers/Guinardó），环境宜人", "租金实惠"],
        "cons": ["地势起伏大，坡道多，部分小区无电梯", "商业多为本地小诊所小超市"]
    },
    "Nou Barris": {
        "sub_barrios": ["Vilapicina", "Porta", "Roquetes", "Verdum", "Ciutat Meridiana"],
        "avg_rent_sqm": 13.8, "index_ref_sqm": 12.0, "avg_sale_sqm": 2700,
        "gross_yield": 6.1, "ibi_yearly_sqm": 5.0, "community_monthly": 40.0,
        "safety_score": 7.2, "livability_score": 7.1, "zone_tensionada": True,
        "pros": ["巴塞罗那租金与总价最低区域", "适合极低预算人群"],
        "cons": ["外来移民比例高，人员较杂", "房子偏旧，离市中心较远"]
    }
}

def normalize_barrio(input_str: str) -> str:
    clean = input_str.strip().lower()
    for key, data in BCN_DATABASE.items():
        if clean in key.lower():
            return key
        for sub in data.get("sub_barrios", []):
            if sub.lower() in clean or clean in sub.lower():
                return key
    return "Eixample"

class PropertyEvaluationRequest(BaseModel):
    intent: str = Field("rent", description="'rent' 或 'buy'")
    rental_type: str = Field("entire", description="'entire' (整租) 或 'room' (单间合租)")
    barrio: str = Field(..., description="行政区或街区名称")
    address: Optional[str] = Field(None, description="具体地址/门牌号")
    price: float = Field(..., description="申请的月租金 (€) 或 房屋销售总价 (€)")
    area_sqm: Optional[float] = Field(None, description="房屋建筑面积 (㎡)")
    bedrooms: Optional[int] = Field(1, description="卧室数量")
    floor_level: Optional[str] = Field("Middle", description="楼层")
    has_elevator: Optional[bool] = Field(True, description="是否有电梯")
    condition: Optional[str] = Field("good", description="房屋状况")
    description: Optional[str] = Field(None, description="自由补充表达或特殊要求") # 支持自由描述

class LegalComplianceRequest(BaseModel):
    barrio: str = Field(..., description="街区名称")
    address: Optional[str] = Field(None, description="具体地址")
    monthly_rent: float = Field(..., description="月租金(欧元)")
    deposit_amount: Optional[float] = Field(None, description="实收押金金额 (€)")
    agency_fee_amount: Optional[float] = Field(None, description="实收中介费金额 (€)")
    contract_type: str = Field("LAU_LONG_TERM", description="'LAU_LONG_TERM' 或 'TEMPORADA'")
    agency_fee_charged_to_tenant: bool = Field(False, description="是否向租客收取了中介费")
    contract_text: Optional[str] = Field(None, description="合同文本或聊天记录")

def call_groq_llm(prompt: str, system_prompt: str) -> Dict[str, Any]:
    clean_key = GROQ_API_KEY.encode('ascii', 'ignore').decode('ascii').strip()
    headers = {
        "Authorization": f"Bearer {clean_key}",
        "Content-Type": "application/json; charset=utf-8"
    }
    
    last_err_msg = ""
    for model_name in MODEL_CANDIDATES:
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
            "max_tokens": 2048
        }
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                timeout=30
            )
            res_data = response.json()
            if response.status_code == 200 and "choices" in res_data:
                return json.loads(res_data["choices"][0]["message"]["content"])
            else:
                last_err_msg = res_data.get("error", {}).get("message", response.text)
        except Exception as e:
            last_err_msg = str(e)
            continue
            
    raise HTTPException(status_code=500, detail=f"Groq LLM 算力引擎调用异常: {last_err_msg}")

@app.post("/api/evaluate")
@app.post("/api/evaluate-property")
async def evaluate_property(req: PropertyEvaluationRequest):
    try:
        matched_barrio = normalize_barrio(req.barrio)
        db = BCN_DATABASE[matched_barrio]
        sqm = req.area_sqm if (req.area_sqm and req.area_sqm > 0) else (20.0 if req.rental_type == "room" else {1: 45.0, 2: 65.0, 3: 85.0}.get(req.bedrooms, 60.0))
        
        adj_factor = 1.0
        if req.condition == "renovated": adj_factor += 0.08
        elif req.condition == "needs_renovation": adj_factor -= 0.12
        if req.floor_level in ["Ático", "顶楼"]: adj_factor += 0.07
        elif req.floor_level in ["Bajo", "底层"] and not req.has_elevator: adj_factor -= 0.10
        if not req.has_elevator and sqm > 40: adj_factor -= 0.08

        if req.rental_type == "room":
            adj_factor *= 1.15

        if req.intent == "buy":
            base_fair_val = db["avg_sale_sqm"] * sqm
            adj_fair_val = round(base_fair_val * adj_factor, 2)
            variance_pct = round(((req.price - adj_fair_val) / adj_fair_val) * 100, 1)
            metrics = {
                "total_cost": f"{round(req.price * 1.125, 2)}€ (含10% ITP及公证费)",
                "gross_yield": f"{round(((db['avg_rent_sqm'] * sqm * 12) / req.price) * 100, 2)}%",
                "avg_district_sale_sqm": f"{db['avg_sale_sqm']}€/㎡"
            }
        else:
            base_fair_val = db["avg_rent_sqm"] * sqm
            adj_fair_val = round(base_fair_val * adj_factor, 2)
            official_limit = round(db["index_ref_sqm"] * sqm, 2)
            variance_pct = round(((req.price - adj_fair_val) / adj_fair_val) * 100, 1)
            metrics = {
                "rental_type": "单间合租 (Habitación)" if req.rental_type == "room" else "整租 (Vivienda Completa)",
                "official_reference_limit": f"{official_limit}€ (加泰参考限价基准)",
                "over_index_pct": f"{round(((req.price - official_limit)/official_limit)*100, 1)}%",
                "sub_barrios_covered": ", ".join(db["sub_barrios"])
            }

        prompt = f'''
请针对巴塞罗那房产生成 JSON 格式评估报告：
- District: {matched_barrio} (包含子区域: {db['sub_barrios']})
- 具体地址: {req.address or '未提供具体门牌'}
- 用户自由表达/补充需求: {req.description or '无补充'}
- 租赁/交易模式: {req.intent} ({req.rental_type})
- 提交价格: {req.price}€ | 公允计算估值: {adj_fair_val}€ | 偏差: {variance_pct}%
- 指标数据: {json.dumps(metrics, ensure_ascii=False)}

返回严格 JSON 结构：
{{
  "valuation_summary": {{
     "rating": "强烈推荐 / 价格合理 / 偏贵溢价 / 不建议考虑",
     "adjusted_fair_value": "{adj_fair_val}€",
     "variance_percentage": "{variance_pct}%",
     "value_verdict": "价格合理度综合评语，结合用户补充表达给出评估"
  }},
  "location_and_address_analysis": "结合具体地址、街区特色以及用户补充要求进行具体分析",
  "district_profile": {{
     "livability_score": "{db['livability_score']}/10",
     "safety_score": "{db['safety_score']}/10",
     "key_pros": {json.dumps(db['pros'], ensure_ascii=False)},
     "key_cons": {json.dumps(db['cons'], ensure_ascii=False)}
  }},
  "actionable_negotiation_strategy": "针对当前房源及价格的具体议价/谈判策略"
}}
'''
        result = call_groq_llm(prompt, "You are an expert Barcelona real estate appraiser. Reply in valid JSON.")
        return {"status": "success", "data": result}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.post("/api/check-rental-risk")
async def check_rental_risk(req: LegalComplianceRequest):
    try:
        matched_barrio = normalize_barrio(req.barrio)
        db = BCN_DATABASE[matched_barrio]
        violations = []
        is_lau = req.contract_type.upper() == "LAU_LONG_TERM"
        
        max_legal_deposit = req.monthly_rent * (3 if is_lau else 2)
        actual_deposit = req.deposit_amount if req.deposit_amount is not None else (req.monthly_rent * 2)
        actual_agency_fee = req.agency_fee_amount if req.agency_fee_amount is not None else (req.monthly_rent * 1.2 if req.agency_fee_charged_to_tenant else 0)

        if is_lau and (req.agency_fee_charged_to_tenant or actual_agency_fee > 0):
            violations.append("【严重违法】依据西班牙 Ley 12/2023 住房法，LAU 长租中介费必须由房东 100% 支付。向租客收取任何名义的服务费/中介费均属于非法行为。")

        if actual_deposit > max_legal_deposit:
            violations.append(f"【押金超标】当前实收押金 ({actual_deposit}€) 超过法定上限 ({max_legal_deposit}€，相当于 {3 if is_lau else 2} 个月租金)，存在资金占用风险。")

        prompt = f'''
请分析巴塞罗那租房法律风险并返回 JSON：
- 区域: {matched_barrio} | 地址: {req.address or '无'}
- 月租: {req.monthly_rent}€ | 提交押金: {actual_deposit}€ | 中介费: {actual_agency_fee}€
- 合同类型: {req.contract_type}
- 合同/备注文本: {req.contract_text or '未提供文本'}
- 判定违法清单: {json.dumps(violations, ensure_ascii=False)}

返回 JSON 结构：
{{
  "overall_risk_level": "RED / YELLOW / GREEN",
  "compliance_verdict": "结论总评",
  "hard_legal_violations": {json.dumps(violations, ensure_ascii=False)},
  "contract_text_analysis": "对用户提供的合同文本/聊天记录的深度霸王条款识别结果",
  "actionable_rights_recovery_steps": [
     "维权与退款/控诉步骤"
  ]
}}
'''
        result = call_groq_llm(prompt, "You are a Spanish rental housing legal expert. Reply in valid JSON.")
        return {"status": "success", "data": result}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8000)