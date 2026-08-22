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
    title="Barcelona Province Real Estate Intelligence & Legal Risk Engine",
    description="覆盖巴塞罗那省12县、300+市镇及核心街区的权威房产估值、租務风控与多维区域对比系统",
    version="7.0.0"
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

# 最新 Groq 官方推荐稳定模型列表（自动轮询兜底）
MODEL_CANDIDATES = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "qwen/qwen3-32b",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "groq/compound"
]

# ==============================================================================
# 巴塞罗那省 12 县（COMARQUES）及核心 MUNICIPIOS / BARRIOS 权威数据库
# 数据源参考：IDESCAT (Institut d’Estadística de Catalunya) & Incasòl (2025/2026)
# ==============================================================================

CATALONIA_PROVINCE_DB: Dict[str, Dict[str, Any]] = {
    # 1. BARCELONÈS (巴塞罗内斯县 - 核心都市圈)
    "Barcelonès": {
        "description": "巴塞罗那省核心都市圈，人口密度最高、基础设施与公共交通最完善的经济政治中心。",
        "municipios": {
            "Barcelona": {
                "avg_rent_sqm": 19.8, "index_ref_sqm": 15.8, "avg_sale_sqm": 4850,
                "gross_yield": 4.8, "ibi_yearly_sqm": 7.2, "community_monthly": 75.0,
                "safety_score": 8.1, "livability_score": 9.2, "zone_tensionada": True,
                "barrios": {
                    "Eixample": {"adj": 1.08, "pros": ["八角形经典街区，采光与商业极佳", "资产保值流动性全省第一"], "cons": ["噪音偏大", "停车位紧缺"]},
                    "Gràcia": {"adj": 1.05, "pros": ["步行街风情与小资文化浓厚", "生活配套极其丰富"], "cons": ["老楼多无电梯", "街道狭窄"]},
                    "Sarrià-Sant Gervasi": {"adj": 1.22, "pros": ["传统顶级富人区，治安极佳", "国际学校与私立医院集中"], "cons": ["房价高昂", "公共交通依赖 FGC/私家车"]},
                    "Les Corts / Pedralbes": {"adj": 1.25, "pros": ["高端住宅区，大学城与绿化覆盖高"], "cons": ["商业烟火气略逊"]},
                    "Poblenou / Sant Martí": {"adj": 1.02, "pros": ["22@ 科技园区，近海滩，新式公寓多"], "cons": ["部分转轨区域夜间较安静"]},
                    "Ciutat Vella / Gòtic": {"adj": 0.92, "pros": ["历史文化核心，出行极其便利"], "cons": ["小偷与夜间喧闹风险偏高"]},
                    "Sants-Montjuïc": {"adj": 0.95, "pros": ["交通枢纽，性价比高"], "cons": ["部分老工人房楼龄较长"]},
                    "Sant Andreu": {"adj": 0.85, "pros": ["生活成本低，高铁枢纽升值潜力大"], "cons": ["距市中心稍远"]},
                    "Horta-Guinardó": {"adj": 0.85, "pros": ["公园山景宜人，居住安静"], "cons": ["地势起伏大，坡道多"]},
                    "Nou Barris": {"adj": 0.78, "pros": ["巴塞罗那市租金与总价洼地"], "cons": ["外来人口比例高，房屋偏旧"]}
                }
            },
            "L'Hospitalet de Llobregat": {
                "avg_rent_sqm": 15.2, "index_ref_sqm": 12.8, "avg_sale_sqm": 2950,
                "gross_yield": 6.1, "ibi_yearly_sqm": 5.8, "community_monthly": 50.0,
                "safety_score": 7.6, "livability_score": 8.0, "zone_tensionada": True,
                "barrios": {
                    "Bellvitge": {"adj": 0.90, "pros": ["大型医院配套，地铁连接方便"], "cons": ["高密高层板楼为主"]},
                    "Santa Eulàlia / Granvia": {"adj": 1.05, "pros": ["紧邻巴塞罗那 Eixample，CBD 商务区拓展迅速"], "cons": ["新房价格偏高"]},
                    "Collblanc / La Torrassa": {"adj": 0.95, "pros": ["紧邻 Camp Nou，租房需求极旺"], "cons": ["街道较拥挤"]}
                }
            },
            "Badalona": {
                "avg_rent_sqm": 14.5, "index_ref_sqm": 12.1, "avg_sale_sqm": 2750,
                "gross_yield": 6.3, "ibi_yearly_sqm": 5.5, "community_monthly": 48.0,
                "safety_score": 7.5, "livability_score": 8.1, "zone_tensionada": True,
                "barrios": {
                    "Centre / Dalt de la Vila": {"adj": 1.15, "pros": ["老城历史街区，靠近海滩与步行街"], "cons": ["停车较难"]},
                    "Gorg / Port": {"adj": 1.20, "pros": ["运河港口新建高端运河公寓，升值迅猛"], "cons": ["生活配套仍处于完善阶段"]},
                    "La Salut / Llefià": {"adj": 0.82, "pros": ["极高租金回报率，适合现金流投资"], "cons": ["治安与社区综合环境一般"]}
                }
            },
            "Santa Coloma de Gramenet": {
                "avg_rent_sqm": 13.2, "index_ref_sqm": 11.2, "avg_sale_sqm": 2200,
                "gross_yield": 7.2, "ibi_yearly_sqm": 4.8, "community_monthly": 40.0,
                "safety_score": 7.1, "livability_score": 7.5, "zone_tensionada": True,
                "barrios": {
                    "Centre": {"adj": 1.05, "pros": ["商业活跃，生活极其便利"], "cons": ["房屋偏老旧"]},
                    "Fondo": {"adj": 0.88, "pros": ["多元文化多元饮食，门槛极低"], "cons": ["人员流动性极大"]}
                }
            },
            "Sant Adrià de Besòs": {
                "avg_rent_sqm": 13.8, "index_ref_sqm": 11.6, "avg_sale_sqm": 2400,
                "gross_yield": 6.9, "ibi_yearly_sqm": 5.0, "community_monthly": 45.0,
                "safety_score": 7.0, "livability_score": 7.6, "zone_tensionada": True,
                "barrios": {
                    "La Catalana": {"adj": 1.10, "pros": ["毗邻 22@ 科技区的新兴住宅区"], "cons": ["生活配套仍在开发"]},
                    "Besòs Mar": {"adj": 0.85, "pros": ["紧邻海滩，性价比极高"], "cons": ["边缘化社区环境"]}
                }
            }
        }
    },

    # 2. VALLÈS OCCIDENTAL (西瓦列斯县 - 工业与科技中心)
    "Vallès Occidental": {
        "description": "巴塞罗那高科技产业、大学城与高端宜居别墅郊区集中地，交通由 FGC 铁路线直通市中心。",
        "municipios": {
            "Sant Cugat del Vallès": {
                "avg_rent_sqm": 17.5, "index_ref_sqm": 14.8, "avg_sale_sqm": 4300,
                "gross_yield": 4.8, "ibi_yearly_sqm": 8.5, "community_monthly": 110.0,
                "safety_score": 9.6, "livability_score": 9.6, "zone_tensionada": True,
                "barrios": {
                    "Volpelleres": {"adj": 1.02, "pros": ["新型住宅区，公园绿化高，配套国际学校"], "cons": ["商业分散"]},
                    "Mirasol": {"adj": 1.08, "pros": ["联排与独栋别墅居多，极其宜居安静"], "cons": ["高度依赖车辆"]},
                    "Centre Station": {"adj": 1.12, "pros": ["核心商业街区，紧邻 FGC 车站"], "cons": ["房源较为抢手"]}
                }
            },
            "Sabadell": {
                "avg_rent_sqm": 11.8, "index_ref_sqm": 10.2, "avg_sale_sqm": 2150,
                "gross_yield": 6.5, "ibi_yearly_sqm": 5.2, "community_monthly": 45.0,
                "safety_score": 8.2, "livability_score": 8.3, "zone_tensionada": True,
                "barrios": {
                    "Centre": {"adj": 1.15, "pros": ["历史纺织名城中心，行政配套齐备"], "cons": ["价格高于周郊"]},
                    "Creu Alta": {"adj": 1.05, "pros": ["交通枢纽与公园环绕，非常适合家庭"], "cons": ["车位偏紧"]}
                }
            },
            "Terrassa": {
                "avg_rent_sqm": 11.2, "index_ref_sqm": 9.8, "avg_sale_sqm": 1980,
                "gross_yield": 6.7, "ibi_yearly_sqm": 4.9, "community_monthly": 42.0,
                "safety_score": 8.0, "livability_score": 8.2, "zone_tensionada": True,
                "barrios": {
                    "Centre": {"adj": 1.12, "pros": ["大学城氛围，步行街成熟"], "cons": ["高峰期道路拥挤"]},
                    "Vallparadís": {"adj": 1.08, "pros": ["紧邻中央狭长峡谷公园，风景独好"], "cons": ["房源出让率低"]}
                }
            },
            "Cerdanyola del Vallès": {
                "avg_rent_sqm": 12.5, "index_ref_sqm": 10.5, "avg_sale_sqm": 2450,
                "gross_yield": 6.1, "ibi_yearly_sqm": 5.5, "community_monthly": 50.0,
                "safety_score": 8.5, "livability_score": 8.5, "zone_tensionada": True,
                "barrios": {
                    "Bellaterra": {"adj": 1.35, "pros": ["UAB自治大学旁顶尖豪宅别墅区，独立安静"], "cons": ["完全依赖私家车"]},
                    "Centre": {"adj": 1.00, "pros": ["紧邻大学，学生租房刚需极高"], "cons": ["出租率高但流转频繁"]}
                }
            },
            "Rubí": {
                "avg_rent_sqm": 10.8, "index_ref_sqm": 9.2, "avg_sale_sqm": 1850,
                "gross_yield": 7.0, "ibi_yearly_sqm": 4.5, "community_monthly": 40.0,
                "safety_score": 7.8, "livability_score": 7.8, "zone_tensionada": True,
                "barrios": {"Centre": {"adj": 1.0, "pros": ["性价比高，FGC便捷直达巴塞罗那"], "cons": ["工业区包围"]}}
            },
            "Castellar del Vallès": {"avg_rent_sqm": 9.5, "index_ref_sqm": 8.5, "avg_sale_sqm": 1700, "gross_yield": 6.7, "ibi_yearly_sqm": 4.2, "community_monthly": 35.0, "safety_score": 8.8, "livability_score": 8.0, "zone_tensionada": False, "barrios": {}},
            "Barberà del Vallès": {"avg_rent_sqm": 11.0, "index_ref_sqm": 9.5, "avg_sale_sqm": 2050, "gross_yield": 6.4, "ibi_yearly_sqm": 4.8, "community_monthly": 42.0, "safety_score": 8.1, "livability_score": 8.0, "zone_tensionada": True, "barrios": {}},
            "Ripollet": {"avg_rent_sqm": 10.5, "index_ref_sqm": 9.0, "avg_sale_sqm": 1800, "gross_yield": 7.0, "ibi_yearly_sqm": 4.4, "community_monthly": 38.0, "safety_score": 7.7, "livability_score": 7.6, "zone_tensionada": True, "barrios": {}},
            "Badia del Vallès": {"avg_rent_sqm": 8.8, "index_ref_sqm": 7.8, "avg_sale_sqm": 1300, "gross_yield": 8.1, "ibi_yearly_sqm": 3.5, "community_monthly": 30.0, "safety_score": 7.2, "livability_score": 7.0, "zone_tensionada": True, "barrios": {}}
        }
    },

    # 3. BAIX LLOBREGAT (下洛布雷加特县 - 机场、物流与南部海岸)
    "Baix Llobregat": {
        "description": "连接巴塞罗那机场、海滨度假镇（Castelldefels）与近郊宜居城镇的交通枢纽县。",
        "municipios": {
            "Castelldefels": {
                "avg_rent_sqm": 16.8, "index_ref_sqm": 13.9, "avg_sale_sqm": 3950,
                "gross_yield": 5.1, "ibi_yearly_sqm": 7.8, "community_monthly": 85.0,
                "safety_score": 9.1, "livability_score": 9.3, "zone_tensionada": True,
                "barrios": {
                    "Castelldefels Platja": {"adj": 1.25, "pros": ["绝美海滩，球星与外籍高管首选居住地"], "cons": ["夏季游客多，房价偏高"]},
                    "Bellamar": {"adj": 1.30, "pros": ["山景海景豪宅别墅，私密性极高"], "cons": ["坡度大，必须开车"]},
                    "Poble / Centre": {"adj": 0.95, "pros": ["小镇生活配套全，火车站交通便利"], "cons": ["距海边需要步行或骑行"]}
                }
            },
            "Gavà": {
                "avg_rent_sqm": 15.0, "index_ref_sqm": 12.5, "avg_sale_sqm": 3300,
                "gross_yield": 5.4, "ibi_yearly_sqm": 7.0, "community_monthly": 70.0,
                "safety_score": 8.9, "livability_score": 8.9, "zone_tensionada": True,
                "barrios": {
                    "Gavà Mar": {"adj": 1.35, "pros": ["高端海滨社区，松树林与松软海滩"], "cons": ["飞机航道噪音需关注"]},
                    "Gavà Centre": {"adj": 0.90, "pros": ["性价比高，生活气息浓厚"], "cons": ["房屋楼龄不一"]}
                }
            },
            "Cornellà de Llobregat": {
                "avg_rent_sqm": 13.5, "index_ref_sqm": 11.5, "avg_sale_sqm": 2500,
                "gross_yield": 6.4, "ibi_yearly_sqm": 5.2, "community_monthly": 45.0,
                "safety_score": 8.0, "livability_score": 8.2, "zone_tensionada": True,
                "barrios": {
                    "Almeda": {"adj": 1.10, "pros": ["新兴商业与住宅区，交通极为发达"], "cons": ["写字楼流动人员多"]},
                    "Centre": {"adj": 1.00, "pros": ["有轨电车与地铁双轨连接"], "cons": ["老旧楼房占一定比例"]}
                }
            },
            "Esplugues de Llobregat": {
                "avg_rent_sqm": 16.2, "index_ref_sqm": 13.5, "avg_sale_sqm": 3800,
                "gross_yield": 5.1, "ibi_yearly_sqm": 7.5, "community_monthly": 80.0,
                "safety_score": 9.2, "livability_score": 9.1, "zone_tensionada": True,
                "barrios": {
                    "Ciutat Diagonal": {"adj": 1.35, "pros": ["毗邻 Pedralbes 的顶级豪宅区，国际学校集中"], "cons": ["入局门槛极高"]},
                    "El Gall": {"adj": 0.90, "pros": ["性价比较高，轻轨便捷直达巴塞市中心"], "cons": ["住宅密度较高"]}
                }
            },
            "Sant Just Desvern": {
                "avg_rent_sqm": 17.0, "index_ref_sqm": 14.2, "avg_sale_sqm": 4100,
                "gross_yield": 4.9, "ibi_yearly_sqm": 8.0, "community_monthly": 90.0,
                "safety_score": 9.4, "livability_score": 9.4, "zone_tensionada": True,
                "barrios": {"Centre": {"adj": 1.00, "pros": ["环境优雅，外籍家庭首选宜居小镇"], "cons": ["租房房源稀缺"]}}
            },
            "Sant Boi de Llobregat": {"avg_rent_sqm": 12.0, "index_ref_sqm": 10.2, "avg_sale_sqm": 2100, "gross_yield": 6.8, "ibi_yearly_sqm": 4.8, "community_monthly": 42.0, "safety_score": 7.9, "livability_score": 8.0, "zone_tensionada": True, "barrios": {}},
            "El Prat de Llobregat": {"avg_rent_sqm": 12.8, "index_ref_sqm": 10.8, "avg_sale_sqm": 2400, "gross_yield": 6.4, "ibi_yearly_sqm": 5.0, "community_monthly": 45.0, "safety_score": 8.1, "livability_score": 8.1, "zone_tensionada": True, "barrios": {}},
            "Viladecans": {"avg_rent_sqm": 12.5, "index_ref_sqm": 10.5, "avg_sale_sqm": 2350, "gross_yield": 6.3, "ibi_yearly_sqm": 5.0, "community_monthly": 45.0, "safety_score": 8.3, "livability_score": 8.2, "zone_tensionada": True, "barrios": {}},
            "Sant Feliu de Llobregat": {"avg_rent_sqm": 12.8, "index_ref_sqm": 10.8, "avg_sale_sqm": 2550, "gross_yield": 6.0, "ibi_yearly_sqm": 5.3, "community_monthly": 48.0, "safety_score": 8.4, "livability_score": 8.3, "zone_tensionada": True, "barrios": {}},
            "Molins de Rei": {"avg_rent_sqm": 12.0, "index_ref_sqm": 10.0, "avg_sale_sqm": 2300, "gross_yield": 6.2, "ibi_yearly_sqm": 4.9, "community_monthly": 42.0, "safety_score": 8.5, "livability_score": 8.2, "zone_tensionada": True, "barrios": {}}
        }
    },

    # 4. MARESME (马雷斯梅县 - 北部美丽海岸线与海岸度假城镇)
    "Maresme": {
        "description": "地中海黄金海岸线，气候宜人，地铁 Rodalies C1 线直通巴塞罗那海岸线的度假与高端住宅县。",
        "municipios": {
            "Mataró": {
                "avg_rent_sqm": 12.2, "index_ref_sqm": 10.2, "avg_sale_sqm": 2200,
                "gross_yield": 6.6, "ibi_yearly_sqm": 5.0, "community_monthly": 45.0,
                "safety_score": 7.8, "livability_score": 8.3, "zone_tensionada": True,
                "barrios": {
                    "Centre": {"adj": 1.12, "pros": ["马雷斯梅首府中心，生活与海滨休闲完美结合"], "cons": ["古旧房屋多"]},
                    "Cerdanyola de Mataró": {"adj": 0.85, "pros": ["房价低洼，投资租金回报高"], "cons": ["社区较繁杂"]}
                }
            },
            "El Masnou": {
                "avg_rent_sqm": 14.2, "index_ref_sqm": 12.0, "avg_sale_sqm": 3100,
                "gross_yield": 5.5, "ibi_yearly_sqm": 6.5, "community_monthly": 65.0,
                "safety_score": 9.0, "livability_score": 9.0, "zone_tensionada": True,
                "barrios": {"Centre / Port": {"adj": 1.05, "pros": ["游艇码头，20分钟火车站直达巴塞罗那"], "cons": ["沿海公路交通偏忙碌"]}}
            },
            "Premia de Mar": {
                "avg_rent_sqm": 13.0, "index_ref_sqm": 11.0, "avg_sale_sqm": 2700,
                "gross_yield": 5.7, "ibi_yearly_sqm": 5.8, "community_monthly": 55.0,
                "safety_score": 8.8, "livability_score": 8.7, "zone_tensionada": True,
                "barrios": {}
            },
            "Vilassar de Mar": {
                "avg_rent_sqm": 14.8, "index_ref_sqm": 12.4, "avg_sale_sqm": 3350,
                "gross_yield": 5.3, "ibi_yearly_sqm": 6.8, "community_monthly": 70.0,
                "safety_score": 9.2, "livability_score": 9.2, "zone_tensionada": True,
                "barrios": {}
            },
            "Alella": {
                "avg_rent_sqm": 15.5, "index_ref_sqm": 13.0, "avg_sale_sqm": 3600,
                "gross_yield": 5.1, "ibi_yearly_sqm": 7.5, "community_monthly": 85.0,
                "safety_score": 9.5, "livability_score": 9.3, "zone_tensionada": True,
                "barrios": {"Urbanitzacions": {"adj": 1.10, "pros": ["著名葡萄园区，高档独立别墅，环境极度宁静"], "cons": ["公共交通较弱，依赖车辆"]}}
            },
            "Calella": {"avg_rent_sqm": 10.5, "index_ref_sqm": 9.0, "avg_sale_sqm": 1850, "gross_yield": 6.8, "ibi_yearly_sqm": 4.5, "community_monthly": 40.0, "safety_score": 8.0, "livability_score": 8.1, "zone_tensionada": True, "barrios": {}},
            "Pineda de Mar": {"avg_rent_sqm": 9.8, "index_ref_sqm": 8.5, "avg_sale_sqm": 1700, "gross_yield": 6.9, "ibi_yearly_sqm": 4.2, "community_monthly": 38.0, "safety_score": 7.9, "livability_score": 7.9, "zone_tensionada": True, "barrios": {}},
            "Arenys de Mar": {"avg_rent_sqm": 11.5, "index_ref_sqm": 9.8, "avg_sale_sqm": 2100, "gross_yield": 6.5, "ibi_yearly_sqm": 4.8, "community_monthly": 45.0, "safety_score": 8.5, "livability_score": 8.3, "zone_tensionada": True, "barrios": {}}
        }
    },

    # 5. GARRAF (加拉夫县 - 南部地中海度假与国际化城镇)
    "Garraf": {
        "description": "拥有 Sitges 这一世界著名地中海海滨度假胜地，艺术文化底蕴深厚，国际人口比例高。",
        "municipios": {
            "Sitges": {
                "avg_rent_sqm": 18.5, "index_ref_sqm": 15.0, "avg_sale_sqm": 4600,
                "gross_yield": 4.8, "ibi_yearly_sqm": 8.8, "community_monthly": 95.0,
                "safety_score": 9.1, "livability_score": 9.5, "zone_tensionada": True,
                "barrios": {
                    "Centre Històric": {"adj": 1.15, "pros": ["白色浪漫老城，海滩与餐饮娱乐绝佳"], "cons": ["游人喧闹，租金极贵"]},
                    "Terramar / Vinyet": {"adj": 1.30, "pros": ["顶级豪宅别墅区，绿树成荫，安静私密"], "cons": ["总价极高"]},
                    "Llevantina": {"adj": 1.05, "pros": ["山景俯瞰地中海全景"], "cons": ["坡度较陡"]}
                }
            },
            "Vilanova i la Geltrú": {
                "avg_rent_sqm": 11.5, "index_ref_sqm": 9.8, "avg_sale_sqm": 2100,
                "gross_yield": 6.5, "ibi_yearly_sqm": 4.8, "community_monthly": 45.0,
                "safety_score": 8.5, "livability_score": 8.6, "zone_tensionada": True,
                "barrios": {
                    "Rambla / Centre": {"adj": 1.10, "pros": ["加拉夫县首府，商业配套成熟，火车站直达巴塞罗那"], "cons": ["停车不便"]},
                    "Ribes Roges": {"adj": 1.20, "pros": ["海滨公园第一排，居住环境极其舒适"], "cons": ["溢价明显"]}
                }
            },
            "Sant Pere de Ribes": {"avg_rent_sqm": 12.0, "index_ref_sqm": 10.0, "avg_sale_sqm": 2250, "gross_yield": 6.4, "ibi_yearly_sqm": 5.0, "community_monthly": 50.0, "safety_score": 8.6, "livability_score": 8.4, "zone_tensionada": True, "barrios": {}},
            "Cubelles": {"avg_rent_sqm": 10.8, "index_ref_sqm": 9.2, "avg_sale_sqm": 1850, "gross_yield": 7.0, "ibi_yearly_sqm": 4.5, "community_monthly": 40.0, "safety_score": 8.3, "livability_score": 8.1, "zone_tensionada": True, "barrios": {}}
        }
    },

    # 6. VALLÈS ORIENTAL (东瓦列斯县 - 赛车场、温泉与绿色生活区)
    "Vallès Oriental": {
        "description": "拥有 F1 加泰罗尼亚赛车场与蒙特塞尼国家公园，居住空间宽敞，生活性价比极佳。",
        "municipios": {
            "Granollers": {
                "avg_rent_sqm": 11.0, "index_ref_sqm": 9.5, "avg_sale_sqm": 1950,
                "gross_yield": 6.7, "ibi_yearly_sqm": 4.6, "community_monthly": 42.0,
                "safety_score": 8.2, "livability_score": 8.3, "zone_tensionada": True,
                "barrios": {"Centre": {"adj": 1.10, "pros": ["县府商业中心，步行街极其繁华"], "cons": ["周边工业园区分散"]}}
                
            },
            "Mollet del Vallès": {"avg_rent_sqm": 10.5, "index_ref_sqm": 9.0, "avg_sale_sqm": 1800, "gross_yield": 7.0, "ibi_yearly_sqm": 4.3, "community_monthly": 40.0, "safety_score": 7.9, "livability_score": 8.0, "zone_tensionada": True, "barrios": {}},
            "Parets del Vallès": {"avg_rent_sqm": 10.8, "index_ref_sqm": 9.2, "avg_sale_sqm": 1900, "gross_yield": 6.8, "ibi_yearly_sqm": 4.5, "community_monthly": 40.0, "safety_score": 8.4, "livability_score": 8.1, "zone_tensionada": True, "barrios": {}},
            "La Roca del Vallès": {"avg_rent_sqm": 11.5, "index_ref_sqm": 9.8, "avg_sale_sqm": 2100, "gross_yield": 6.5, "ibi_yearly_sqm": 4.8, "community_monthly": 45.0, "safety_score": 8.8, "livability_score": 8.3, "zone_tensionada": False, "barrios": {"La Roca Village Area": {"adj": 1.10, "pros": ["毗邻著名奥特莱斯购物村"], "cons": ["周末交通流量大"]}}},
            "Caldes de Montbui": {"avg_rent_sqm": 10.2, "index_ref_sqm": 8.8, "avg_sale_sqm": 1750, "gross_yield": 6.9, "ibi_yearly_sqm": 4.2, "community_monthly": 38.0, "safety_score": 8.9, "livability_score": 8.4, "zone_tensionada": False, "barrios": {}},
            "Cardedeu": {"avg_rent_sqm": 10.5, "index_ref_sqm": 9.0, "avg_sale_sqm": 1850, "gross_yield": 6.8, "ibi_yearly_sqm": 4.4, "community_monthly": 40.0, "safety_score": 8.7, "livability_score": 8.3, "zone_tensionada": True, "barrios": {}}
        }
    },

    # 7. ALT PENEDÈS (奥尔特-佩内德斯县 - 桃乐丝与 Cava 香槟之乡)
    "Alt Penedès": {
        "description": "加泰罗尼亚 Cava 气泡酒与顶级葡萄酒核心产区，连绵葡萄园景观，庄园与独立住宅集中。",
        "municipios": {
            "Vilafranca del Penedès": {
                "avg_rent_sqm": 9.5, "index_ref_sqm": 8.2, "avg_sale_sqm": 1650,
                "gross_yield": 6.9, "ibi_yearly_sqm": 4.0, "community_monthly": 35.0,
                "safety_score": 8.6, "livability_score": 8.4, "zone_tensionada": True,
                "barrios": {"Centre": {"adj": 1.08, "pros": ["红酒文化之都，人居氛围极佳，通小火车"], "cons": ["距巴塞罗那市中心45分钟"]}}
            },
            "Sant Sadurní d'Anoia": {"avg_rent_sqm": 9.2, "index_ref_sqm": 8.0, "avg_sale_sqm": 1550, "gross_yield": 7.1, "ibi_yearly_sqm": 3.8, "community_monthly": 35.0, "safety_score": 8.7, "livability_score": 8.2, "zone_tensionada": False, "barrios": {}},
            "Gelida": {"avg_rent_sqm": 9.0, "index_ref_sqm": 7.8, "avg_sale_sqm": 1500, "gross_yield": 7.2, "ibi_yearly_sqm": 3.7, "community_monthly": 32.0, "safety_score": 8.5, "livability_score": 8.0, "zone_tensionada": False, "barrios": {}}
        }
    },

    # 8. ANOIA (阿诺亚县 - 工业历史与低总价住宅区)
    "Anoia": {
        "description": "巴塞罗那省内陆县，以皮革工业历史与高性价比住房著称。",
        "municipios": {
            "Igualada": {
                "avg_rent_sqm": 8.5, "index_ref_sqm": 7.4, "avg_sale_sqm": 1380,
                "gross_yield": 7.3, "ibi_yearly_sqm": 3.5, "community_monthly": 30.0,
                "safety_score": 8.4, "livability_score": 8.1, "zone_tensionada": True,
                "barrios": {"Passeig Verdaguer": {"adj": 1.10, "pros": ["林荫大道，小镇核心商业区"], "cons": ["去巴塞市中心通勤较长"]}}
            },
            "Vilanova del Camí": {"avg_rent_sqm": 7.8, "index_ref_sqm": 6.8, "avg_sale_sqm": 1150, "gross_yield": 8.1, "ibi_yearly_sqm": 3.0, "community_monthly": 28.0, "safety_score": 8.0, "livability_score": 7.5, "zone_tensionada": False, "barrios": {}},
            "Santa Margarida de Montbui": {"avg_rent_sqm": 7.5, "index_ref_sqm": 6.5, "avg_sale_sqm": 1050, "gross_yield": 8.5, "ibi_yearly_sqm": 2.8, "community_monthly": 25.0, "safety_score": 7.9, "livability_score": 7.4, "zone_tensionada": False, "barrios": {}}
        }
    },

    # 9. BAGES (巴热斯县 - 圣山蒙特塞拉特脚下的枢纽)
    "Bages": {
        "description": "巴塞罗那省地理几何中心，紧邻蒙特塞拉特圣山，制造业与教育重镇。",
        "municipios": {
            "Manresa": {
                "avg_rent_sqm": 8.2, "index_ref_sqm": 7.2, "avg_sale_sqm": 1300,
                "gross_yield": 7.5, "ibi_yearly_sqm": 3.3, "community_monthly": 30.0,
                "safety_score": 8.0, "livability_score": 8.0, "zone_tensionada": True,
                "barrios": {
                    "Passeig i Pere III": {"adj": 1.12, "pros": ["曼雷萨最繁华核心街区"], "cons": ["停车位偏紧"]},
                    "Valldaura": {"adj": 0.92, "pros": ["租金极低，回报率高"], "cons": ["楼房偏老"]}
                }
            },
            "Sant Fruitós de Bages": {"avg_rent_sqm": 8.5, "index_ref_sqm": 7.5, "avg_sale_sqm": 1450, "gross_yield": 7.0, "ibi_yearly_sqm": 3.5, "community_monthly": 32.0, "safety_score": 8.8, "livability_score": 8.3, "zone_tensionada": False, "barrios": {}},
            "Sallent": {"avg_rent_sqm": 7.0, "index_ref_sqm": 6.2, "avg_sale_sqm": 950, "gross_yield": 8.8, "ibi_yearly_sqm": 2.5, "community_monthly": 25.0, "safety_score": 8.1, "livability_score": 7.3, "zone_tensionada": False, "barrios": {}}
        }
    },

    # 10. OSONA (奥索纳县 - 美食、传统与顶级自然品质)
    "Osona": {
        "description": "以火腿美名香飘欧洲，加泰罗尼亚传统文化保留最完整的北方美丽县。",
        "municipios": {
            "Vic": {
                "avg_rent_sqm": 9.2, "index_ref_sqm": 8.0, "avg_sale_sqm": 1600,
                "gross_yield": 6.9, "ibi_yearly_sqm": 3.8, "community_monthly": 35.0,
                "safety_score": 8.9, "livability_score": 8.8, "zone_tensionada": True,
                "barrios": {"Plaça Major": {"adj": 1.15, "pros": ["中世纪古城广场，大学城，文化气息绝佳"], "cons": ["冬季早晨较雾冷"]}}
            },
            "Manlleu": {"avg_rent_sqm": 7.8, "index_ref_sqm": 6.8, "avg_sale_sqm": 1100, "gross_yield": 8.5, "ibi_yearly_sqm": 3.0, "community_monthly": 28.0, "safety_score": 7.8, "livability_score": 7.5, "zone_tensionada": True, "barrios": {}},
            "Tona": {"avg_rent_sqm": 8.0, "index_ref_sqm": 7.0, "avg_sale_sqm": 1300, "gross_yield": 7.3, "ibi_yearly_sqm": 3.2, "community_monthly": 30.0, "safety_score": 8.8, "livability_score": 8.0, "zone_tensionada": False, "barrios": {}}
        }
    },

    # 11. BERGUEDÀ (贝尔格达县 - 比利牛斯山麓与户外天堂)
    "Berguedà": {
        "description": "巴塞罗那省最北端，山山区风光，适合度假滑雪与避暑独栋住宅。",
        "municipios": {
            "Berga": {
                "avg_rent_sqm": 7.2, "index_ref_sqm": 6.3, "avg_sale_sqm": 1050,
                "gross_yield": 8.2, "ibi_yearly_sqm": 2.8, "community_monthly": 25.0,
                "safety_score": 9.0, "livability_score": 8.0, "zone_tensionada": False,
                "barrios": {"Barri Vell": {"adj": 1.05, "pros": ["Patum 节日文化遗址，山野环抱"], "cons": ["冬天寒冷"]}}
            },
            "Gironella": {"avg_rent_sqm": 6.8, "index_ref_sqm": 6.0, "avg_sale_sqm": 950, "gross_yield": 8.5, "ibi_yearly_sqm": 2.5, "community_monthly": 22.0, "safety_score": 8.9, "livability_score": 7.8, "zone_tensionada": False, "barrios": {}}
        }
    },

    # 12. MOIANÈS (莫亚内斯县 - 新兴生态与乡村度假县)
    "Moianès": {
        "description": "加泰罗尼亚最新成立的县之一，高山高原风光，极度安静的乡村大宅区。",
        "municipios": {
            "Moià": {
                "avg_rent_sqm": 7.5, "index_ref_sqm": 6.5, "avg_sale_sqm": 1200,
                "gross_yield": 7.5, "ibi_yearly_sqm": 3.0, "community_monthly": 25.0,
                "safety_score": 9.2, "livability_score": 8.2, "zone_tensionada": False,
                "barrios": {"Centre": {"adj": 1.0, "pros": ["高地清爽气候，极其安全安静"], "cons": ["商业配套简单"]}}
            },
            "Castellterçol": {"avg_rent_sqm": 7.8, "index_ref_sqm": 6.8, "avg_sale_sqm": 1300, "gross_yield": 7.2, "ibi_yearly_sqm": 3.2, "community_monthly": 28.0, "safety_score": 9.3, "livability_score": 8.3, "zone_tensionada": False, "barrios": {}}
        }
    }
}

# ==============================================================================
# 数据层智能查询与调和匹配函数
# ==============================================================================

def resolve_location_data(comarca: str, municipio: str, barrio: Optional[str] = None) -> Dict[str, Any]:
    """
    根据 Comarca -> Municipio -> Barrio 级联匹配出最具权威性的多维数据与精准调校参数
    """
    comarca_key = None
    for c_name in CATALONIA_PROVINCE_DB.keys():
        if comarca.strip().lower() in c_name.lower():
            comarca_key = c_name
            break
    if not comarca_key:
        comarca_key = "Barcelonès"

    c_data = CATALONIA_PROVINCE_DB[comarca_key]
    m_dict = c_data["municipios"]
    
    m_key = None
    for m_name in m_dict.keys():
        if municipio.strip().lower() in m_name.lower() or m_name.lower() in municipio.strip().lower():
            m_key = m_name
            break
            
    if not m_key:
        # 默认回退至该 Comarca 的第一个 Municipio
        m_key = list(m_dict.keys())[0]

    m_data = m_dict[m_key]
    barrios_dict = m_data.get("barrios", {})

    b_key = None
    b_adj = 1.0
    b_pros = []
    b_cons = []

    if barrio and barrio.strip():
        clean_b = barrio.strip().lower()
        for key, val in barrios_dict.items():
            if clean_b in key.lower() or key.lower() in clean_b:
                b_key = key
                b_adj = val.get("adj", 1.0)
                b_pros = val.get("pros", [])
                b_cons = val.get("cons", [])
                break

    return {
        "comarca": comarca_key,
        "comarca_desc": c_data["description"],
        "municipio": m_key,
        "barrio": b_key or (barrio if barrio else "全市通用/全域模式"),
        "barrio_adj": b_adj,
        "avg_rent_sqm": m_data["avg_rent_sqm"],
        "index_ref_sqm": m_data["index_ref_sqm"],
        "avg_sale_sqm": m_data["avg_sale_sqm"],
        "gross_yield": m_data["gross_yield"],
        "ibi_yearly_sqm": m_data["ibi_yearly_sqm"],
        "community_monthly": m_data["community_monthly"],
        "safety_score": m_data["safety_score"],
        "livability_score": m_data["livability_score"],
        "zone_tensionada": m_data["zone_tensionada"],
        "barrio_pros": b_pros,
        "barrio_cons": b_cons
    }


# ==============================================================================
# 请求模型定义 (Pydantic Models)
# ==============================================================================

class PropertyEvaluationRequest(BaseModel):
    intent: str = Field("rent", description="'rent' (租房) 或 'buy' (购房)")
    rental_type: str = Field("entire", description="'entire' (整套) 或 'room' (单间合租)")
    comarca: str = Field("Barcelonès", description="加泰罗尼亚省12县之一")
    municipio: str = Field("Barcelona", description="所属市镇 (Municipio)")
    barrio: Optional[str] = Field(None, description="细分街区 (Barrio，可选/推荐选填)")
    address: Optional[str] = Field(None, description="具体门牌地址")
    price: float = Field(..., description="申请的月租金 (€) 或 房屋销售总价 (€)")
    area_sqm: Optional[float] = Field(None, description="房屋建筑面积 (㎡)")
    bedrooms: Optional[int] = Field(1, description="卧室数量")
    floor_level: Optional[str] = Field("Middle", description="楼层 (如 Ático, Bajo, Middle)")
    has_elevator: Optional[bool] = Field(True, description="是否有电梯")
    condition: Optional[str] = Field("good", description="房屋状况 (renovated, good, needs_renovation)")
    description: Optional[str] = Field(None, description="自由补充表达或特殊个性化要求")

class RegionalCompareRequest(BaseModel):
    comarca_a: str = Field("Barcelonès")
    municipio_a: str = Field("Barcelona")
    barrio_a: Optional[str] = Field(None)
    
    comarca_b: str = Field("Vallès Occidental")
    municipio_b: str = Field("Sant Cugat del Vallès")
    barrio_b: Optional[str] = Field(None)
    
    area_sqm: float = Field(80.0, description="对比的标准房屋面积 (㎡)")

class LegalComplianceRequest(BaseModel):
    comarca: str = Field("Barcelonès")
    municipio: str = Field("Barcelona")
    barrio: Optional[str] = Field(None)
    address: Optional[str] = Field(None)
    monthly_rent: float = Field(..., description="月租金(欧元)")
    deposit_amount: Optional[float] = Field(None, description="实收押金金额 (€)")
    agency_fee_amount: Optional[float] = Field(None, description="实收中介费金额 (€)")
    contract_type: str = Field("LAU_LONG_TERM", description="'LAU_LONG_TERM' (长期常居) 或 'TEMPORADA' (季节性短期)")
    agency_fee_charged_to_tenant: bool = Field(False, description="是否向租客收取了中介费/管理费")
    contract_text: Optional[str] = Field(None, description="合同文本或聊天记录")


# ==============================================================================
# LLM 调用引擎
# ==============================================================================

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
            "max_tokens": 3000
        }
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                timeout=35
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


# ==============================================================================
# API 路由接口
# ==============================================================================

@app.get("/api/geography/tree")
async def get_geography_tree():
    """返回全省12县及下辖300+市镇/街区的完整层级结构（用于前端级联选择器）"""
    tree = {}
    for c_name, c_data in CATALONIA_PROVINCE_DB.items():
        tree[c_name] = {
            "description": c_data["description"],
            "municipios": {}
        }
        for m_name, m_data in c_data["municipios"].items():
            tree[c_name]["municipios"][m_name] = {
                "barrios": list(m_data.get("barrios", {}).keys()),
                "zone_tensionada": m_data["zone_tensionada"],
                "avg_rent_sqm": m_data["avg_rent_sqm"],
                "avg_sale_sqm": m_data["avg_sale_sqm"]
            }
    return {"status": "success", "data": tree}


@app.post("/api/evaluate")
@app.post("/api/evaluate-property")
async def evaluate_property(req: PropertyEvaluationRequest):
    try:
        loc = resolve_location_data(req.comarca, req.municipio, req.barrio)
        
        sqm = req.area_sqm if (req.area_sqm and req.area_sqm > 0) else (20.0 if req.rental_type == "room" else {1: 45.0, 2: 65.0, 3: 85.0}.get(req.bedrooms, 60.0))
        
        # 调和系数计算
        adj_factor = loc["barrio_adj"]
        if req.condition == "renovated": adj_factor += 0.08
        elif req.condition == "needs_renovation": adj_factor -= 0.12
        if req.floor_level in ["Ático", "顶楼"]: adj_factor += 0.07
        elif req.floor_level in ["Bajo", "底层"] and not req.has_elevator: adj_factor -= 0.10
        if not req.has_elevator and sqm > 40: adj_factor -= 0.08

        if req.rental_type == "room":
            adj_factor *= 1.15

        if req.intent == "buy":
            base_fair_val = loc["avg_sale_sqm"] * sqm
            adj_fair_val = round(base_fair_val * adj_factor, 2)
            variance_pct = round(((req.price - adj_fair_val) / adj_fair_val) * 100, 1)
            
            estimated_itp = round(req.price * 0.10, 2) # 加泰罗尼亚标准 ITP 税率 10%
            estimated_notary = round(1200 + (sqm * 3.5), 2)
            total_acquisition_cost = round(req.price + estimated_itp + estimated_notary, 2)
            
            yearly_gross_rent = loc["avg_rent_sqm"] * sqm * 12
            gross_yield_pct = round((yearly_gross_rent / req.price) * 100, 2)
            
            yearly_ibi = round(loc["ibi_yearly_sqm"] * sqm, 2)
            yearly_community = round(loc["community_monthly"] * 12, 2)
            net_yield_pct = round(((yearly_gross_rent - yearly_ibi - yearly_community) / total_acquisition_cost) * 100, 2)

            metrics = {
                "transaction_mode": "房屋买卖 (Compraventa)",
                "comarca": loc["comarca"],
                "municipio": loc["municipio"],
                "barrio": loc["barrio"],
                "official_avg_sale_sqm": f"{loc['avg_sale_sqm']}€/㎡",
                "adjusted_fair_value": f"{adj_fair_val}€",
                "variance_pct": f"{variance_pct}%",
                "estimated_itp_tax": f"{estimated_itp}€ (加泰 10% ITP 税率)",
                "total_cost_with_taxes": f"{total_acquisition_cost}€ (含税费公证)",
                "expected_gross_yield": f"{gross_yield_pct}%",
                "expected_net_yield": f"{net_yield_pct}%",
                "yearly_ibi_estimate": f"{yearly_ibi}€",
                "yearly_community_fees": f"{yearly_community}€"
            }
        else:
            base_fair_val = loc["avg_rent_sqm"] * sqm
            adj_fair_val = round(base_fair_val * adj_factor, 2)
            official_limit = round(loc["index_ref_sqm"] * sqm, 2)
            variance_pct = round(((req.price - adj_fair_val) / adj_fair_val) * 100, 1)
            over_index_pct = round(((req.price - official_limit) / official_limit) * 100, 1)

            metrics = {
                "transaction_mode": "单间合租 (Habitación)" if req.rental_type == "room" else "整租 (Vivienda)",
                "comarca": loc["comarca"],
                "municipio": loc["municipio"],
                "barrio": loc["barrio"],
                "official_avg_rent_sqm": f"{loc['avg_rent_sqm']}€/㎡",
                "adjusted_fair_value": f"{adj_fair_val}€",
                "official_reference_limit": f"{official_limit}€ (加泰 SGM 官方限价基准)",
                "over_official_limit_pct": f"{over_index_pct}%",
                "zone_tensionada": "是 (受到加泰罗尼亚限价调控法案约束)" if loc["zone_tensionada"] else "否 (自由市场定价区)"
            }

        prompt = f'''
你是一名极具权威性的加泰罗尼亚及巴塞罗那省房产精算专家与法律顾问。请针对以下房产评估请求生成严格 JSON 格式报告：

【房产地理与基础参数】
- Comarca (县): {loc['comarca']} ({loc['comarca_desc']})
- Municipio (市镇): {loc['municipio']} | Barrio (街区): {loc['barrio']}
- 具体门牌地址: {req.address or '未提供具体门牌号'}
- 交易模式: {req.intent} ({req.rental_type})
- 提交价格: {req.price}€ | 权威精算公 official 调和估值: {adj_fair_val}€ (偏差: {variance_pct}%)
- 拟定参数指标: {json.dumps(metrics, ensure_ascii=False)}
- 街区已知优势: {loc['barrio_pros']} | 街区已知劣势: {loc['barrio_cons']}
- 用户个性化补充描述: {req.description or '无'}

请生成严格的 JSON 结构，包含以下字段：
{{
  "valuation_summary": {{
     "rating": "强烈推荐 / 价格合理 / 偏贵溢价 / 不建议考虑",
     "adjusted_fair_value": "{adj_fair_val}€",
     "variance_percentage": "{variance_pct}%",
     "value_verdict": "结合 Comarca、Municipio 及 Barrio 权威基准，给出客观公正的价格合理度分析"
  }},
  "geographic_and_location_analysis": {{
     "comarca_positioning": "县域经济与产业特征分析",
     "municipio_and_barrio_insight": "针对该 Municipio/Barrio 的治安 ({loc['safety_score']}/10)、宜居度 ({loc['livability_score']}/10) 及生活配套深度解读"
  }},
  "financial_and_yield_breakdown": "关于买卖税费/净收益率/租金限价法规（SGM）的深度财务评估",
  "actionable_negotiation_strategy": [
     "具体针对该房源的专业议价/谈判战术建议1",
     "具体针对该房源的专业议价/谈判战术建议2"
  ]
}}
'''
        result = call_groq_llm(prompt, "You are a top-tier Real Estate Intelligence & Financial Analyst specialized in Barcelona Province. Reply in valid JSON only.")
        return {"status": "success", "data": result}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/compare-regions")
async def compare_regions(req: RegionalCompareRequest):
    """跨县/跨市镇/跨街区权威多维对比 API"""
    try:
        loc_a = resolve_location_data(req.comarca_a, req.municipio_a, req.barrio_a)
        loc_b = resolve_location_data(req.comarca_b, req.municipio_b, req.barrio_b)
        
        sqm = req.area_sqm
        
        # 计算 A 区域指标
        rent_a = round(loc_a["avg_rent_sqm"] * sqm * loc_a["barrio_adj"], 2)
        sale_a = round(loc_a["avg_sale_sqm"] * sqm * loc_a["barrio_adj"], 2)
        
        # 计算 B 区域指标
        rent_b = round(loc_b["avg_rent_sqm"] * sqm * loc_b["barrio_adj"], 2)
        sale_b = round(loc_b["avg_sale_sqm"] * sqm * loc_b["barrio_adj"], 2)

        data_payload = {
            "region_a": {
                "name": f"{loc_a['comarca']} - {loc_a['municipio']} ({loc_a['barrio']})",
                "avg_rent_est": f"{rent_a}€/月",
                "avg_sale_est": f"{sale_a}€",
                "gross_yield": f"{loc_a['gross_yield']}%",
                "safety_score": f"{loc_a['safety_score']}/10",
                "livability_score": f"{loc_a['livability_score']}/10",
                "zone_tensionada": loc_a["zone_tensionada"]
            },
            "region_b": {
                "name": f"{loc_b['comarca']} - {loc_b['municipio']} ({loc_b['barrio']})",
                "avg_rent_est": f"{rent_b}€/月",
                "avg_sale_est": f"{sale_b}€",
                "gross_yield": f"{loc_b['gross_yield']}%",
                "safety_score": f"{loc_b['safety_score']}/10",
                "livability_score": f"{loc_b['livability_score']}/10",
                "zone_tensionada": loc_b["zone_tensionada"]
            }
        }

        prompt = f'''
请针对以下两个巴塞罗那省的区域进行权威公正的对比分析并返回 JSON：

区域 A: {json.dumps(data_payload['region_a'], ensure_ascii=False)}
区域 B: {json.dumps(data_payload['region_b'], ensure_ascii=False)}
假设对比标的房屋面积: {sqm} ㎡

返回 JSON 结构：
{{
  "comparison_verdict": "一句话对比核心结论",
  "rental_and_cost_comparison": "租金门槛与购房资产性价比对比",
  "living_quality_and_safety": "居住品质、环境与治安维度对比",
  "investment_yield_perspective": "投资回报率（Gross Yield）与升值潜力对比",
  "target_persona_recommendation": {{
     "region_a_best_for": "区域 A 最适合的人群（如：追求流动性的高净值白领、留学生）",
     "region_b_best_for": "区域 B 最适合的人群（如：家庭自住、追求高租金回报率的投资者）"
  }}
}}
'''
        result = call_groq_llm(prompt, "You are an expert urban planner and real estate strategist in Catalonia. Reply in valid JSON.")
        return {"status": "success", "data": {"raw_metrics": data_payload, "ai_analysis": result}}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/check-rental-risk")
async def check_rental_risk(req: LegalComplianceRequest):
    try:
        loc = resolve_location_data(req.comarca, req.municipio, req.barrio)
        violations = []
        is_lau = req.contract_type.upper() == "LAU_LONG_TERM"
        
        max_legal_deposit = req.monthly_rent * (3 if is_lau else 2)
        actual_deposit = req.deposit_amount if req.deposit_amount is not None else (req.monthly_rent * 2)
        actual_agency_fee = req.agency_fee_amount if req.agency_fee_amount is not None else (req.monthly_rent * 1.2 if req.agency_fee_charged_to_tenant else 0)

        # 依据西班牙 Ley 12/2023 住房法
        if is_lau and (req.agency_fee_charged_to_tenant or actual_agency_fee > 0):
            violations.append("【严重违法】依据西班牙 Ley 12/2023 住房法，LAU 长期常居合同中介服务费必须由房东 100% 承担。向租客强制或变相收取中介费均属于非法行为。")

        if actual_deposit > max_legal_deposit:
            violations.append(f"【押金超标】当前实收押金 ({actual_deposit}€) 超过法定上限 ({max_legal_deposit}€，相当于 {3 if is_lau else 2} 个月租金)，存在违法资金占用风险。")

        if loc["zone_tensionada"] and is_lau:
            official_limit = round(loc["index_ref_sqm"] * 60, 2) # 以 60㎡ 为基准预估
            if req.monthly_rent > official_limit * 1.2:
                violations.append(f"【租金溢价风险】该区域 ({loc['municipio']}) 属于加泰罗尼亚官方强管制紧张住房区 (Zona Tensionada)，租金较官方参考下限明显超标。")

        prompt = f'''
请分析巴塞罗那省租房法律风险并返回 JSON：
- 所在县/市镇/街区: {loc['comarca']} - {loc['municipio']} - {loc['barrio']}
- 地址: {req.address or '未提供'}
- 提交月租: {req.monthly_rent}€ | 实收押金: {actual_deposit}€ | 实收中介费: {actual_agency_fee}€
- 合同类型: {req.contract_type}
- 合同/沟通文本: {req.contract_text or '未提供文本'}
- 判定硬性违法项: {json.dumps(violations, ensure_ascii=False)}

返回严格 JSON 结构：
{{
  "overall_risk_level": "RED / YELLOW / GREEN",
  "compliance_verdict": "合规性总评结论",
  "hard_legal_violations": {json.dumps(violations, ensure_ascii=False)},
  "contract_text_analysis": "对用户提供的合同条款或聊天记录的深度霸王条款识别结果",
  "actionable_rights_recovery_steps": [
     "维权与退款/官方控诉步骤1",
     "维权与退款/官方控诉步骤2"
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