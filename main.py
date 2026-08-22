import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import requests

app = FastAPI()

# 允许 Vercel 前端跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

class EvaluationRequest(BaseModel):
    eval_type: str  # 'rent' or 'investment'
    lease_mode: str # 'complete', 'room', 'temporal', 'coliving'
    district: str
    neighborhood: Optional[str] = ""
    address: Optional[str] = ""
    price: float
    size: float
    bedrooms: int
    bathrooms: Optional[int] = 1
    floor: Optional[str] = "中间楼层 (Planta Media)"
    condition: str
    elevator: bool
    balcony: bool
    furnished: Optional[str] = "带全套家具"
    energy_certificate: Optional[str] = "未知"
    user_custom_requirements: Optional[str] = "" # 用户自定义需求（用于匹配/分析）

@app.post("/api/evaluate")
async def evaluate_property(req: EvaluationRequest):
    if not GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="Groq API Key not configured in environment variables.")

    prompt = f"""
你是一名巴塞罗那高级房产精算师兼租务法律专家。请根据以下用户输入的具体房产数据，进行极度深入、专业的分析，并输出一份完整的评估报告。

【房产/需求详细数据】
- 评估类型: {req.eval_type}
- 租赁模式: {req.lease_mode}
- 行政区 (Distrito): {req.district}
- 具体街区 (Barrio): {req.neighborhood}
- 具体地址: {req.address}
- 价格: {req.price} €/月 (或总价)
- 建筑面积: {req.size} ㎡
- 户型: {req.bedrooms} 室 {req.bathrooms} 卫
- 所在楼层: {req.floor}
- 房屋状况: {req.condition}
- 设施配备: 电梯={req.elevator}, 阳台/露台={req.balcony}, 家具={req.furnished}, 能源等级={req.energy_certificate}
- 用户个性化需求与补充说明: {req.user_custom_requirements}

【请按以下标准 Markdown 格式输出深度报告，拒绝简短回答】

## 📊 1. 市场估值与溢价分析
- **合理价格区间**: 计算该区域/街区同类房源的市场均价（单价 €/㎡）并给出合理的预估区间。
- **溢价率评估**: 分析当前价格 (€{req.price}) 是偏高、合理还是低于市场价，说明原因（结合楼层、电梯、装修等）。

## ⚖️ 2. 加泰罗尼亚租房法律与风控评估
- **租金限制区 (Zona Tensionada) 法规遵从度**: 评估该房源是否属于受西班牙/加泰罗尼亚新 housing law 限制区域。
- **押金与中介费合规性**: 明确告知用户在 5年/7年 长租合同下，中介费是否应由房东支付，防止被骗。
- **潜在风险提示**: 针对楼层（如底层 Low floor 湿气/盗窃风险、无电梯高层）、合租/临时合同条款漏洞等给出具体防范建议。

## 🎯 3. 综合打分与决策建议
- **性价比得分**: X / 10
- **居住/投资适合度**: 详细分析
- **议价/谈判策略**: 给出具体的砍价切入点（如利用能源等级、楼层缺陷或装修状况）。

## 🏠 4. 智能匹配与同类房源推荐
根据用户的预算与要求，推荐 2-3 个在巴塞罗那该区域（或性价比更高的替代街区）的寻找房源策略与具体区域/小区推荐（包含筛选关键字与大致价格范畴）。
"""

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": "你是一个巴塞罗那本地的专业房产与法律 AI 助手。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.5,
        "max_tokens": 2500
    }

    try:
        response = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=60)
        res_data = response.json()
        if "choices" in res_data and len(res_data["choices"]) > 0:
            analysis_markdown = res_data["choices"][0]["message"]["content"]
            return {"status": "success", "analysis": analysis_markdown}
        else:
            raise HTTPException(status_code=500, detail="AI Service Response Error")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
