"""AI店长 v1.2 - FastAPI REST API

提供健康检查、图片打包、发货SOP、仪表盘、流量分析接口。
运行: uvicorn api:app --host 0.0.0.0 --port 8000
"""
import json
import logging
import os
import sys
from datetime import datetime, date
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import Database
from modules.image_pack import generate_image_pack, get_pack_zip_path
from modules.shipping import SHIPPING_STATUSES, build_pdd_order_note, create_from_draft
from modules.dashboard_data import build_dashboard_data
from config import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="AI店长 API", version="1.2")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

cfg_path = os.path.join(os.path.dirname(__file__), "config.ini")
app_cfg = load_config(cfg_path).as_dict()
db_path = os.path.join(os.path.dirname(__file__), app_cfg.get("database", {}).get("path", "data/ai_storekeeper.db"))
db = Database(db_path)

STORAGE_DIR = Path(__file__).parent / "storage"
STORAGE_DIR.mkdir(exist_ok=True)


# ── 健康检查 ──
@app.get("/health")
def health():
    ok = True
    errors = []
    # DB check
    try:
        db.get_stats()
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {e}"
        ok = False
        errors.append(str(e))
    # Storage check
    try:
        (STORAGE_DIR / "image-packs").mkdir(parents=True, exist_ok=True)
        storage_status = "ok"
    except Exception as e:
        storage_status = f"error: {e}"
        ok = False
    return {
        "ok": ok,
        "db": db_status,
        "storage": storage_status,
        "time": datetime.now().isoformat(),
        "errors": errors,
    }


# ── 图片打包 ──
class ImagePackRequest(BaseModel):
    opportunity: dict
    product_family_id: str = ""

@app.post("/image-pack/generate")
def create_image_pack(req: ImagePackRequest):
    try:
        result = generate_image_pack(req.opportunity, req.product_family_id)
        # 持久化记录
        db.save_image_pack({
            "product_family_id": req.product_family_id or str(req.opportunity.get("id", "")),
            "title": result["title"],
            "source": result["manifest"]["source"],
            "image_count": result["image_count"],
            "failed_count": result["failed"],
            "pack_path": result["zip_path"],
        })
        return {"ok": True, "data": result}
    except Exception as e:
        logger.exception("Image pack failed")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/image-pack/{pack_id}/download")
def download_image_pack(pack_id: str):
    path = get_pack_zip_path(pack_id)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="Pack not found")
    return FileResponse(path, media_type="application/zip", filename=f"{pack_id}.zip")

@app.get("/image-pack/list")
def list_image_packs(product_family_id: str = "", limit: int = 20):
    packs = db.get_image_packs(product_family_id or None, limit)
    return {"ok": True, "data": packs}


# ── 发货SOP ──
class ShippingOrderCreate(BaseModel):
    draft_id: str = ""
    product_family_id: str = ""
    xianyu_order_no: str = ""
    buyer_name: str = ""
    buyer_phone: str = ""
    buyer_address: str = ""
    pdd_goods_url: str = ""
    pdd_sku: str = ""
    cost_price: float = 0
    sale_price: float = 0
    profit: float = 0

class ShippingOrderUpdate(BaseModel):
    shipping_status: Optional[str] = None
    xianyu_order_no: Optional[str] = None
    buyer_name: Optional[str] = None
    buyer_phone: Optional[str] = None
    buyer_address: Optional[str] = None
    pdd_goods_url: Optional[str] = None
    pdd_sku: Optional[str] = None
    pdd_order_no: Optional[str] = None
    tracking_no: Optional[str] = None
    tracking_company: Optional[str] = None
    remark: Optional[str] = None

@app.post("/shipping/orders")
def create_shipping_order(req: ShippingOrderCreate):
    order_id = db.create_shipping_order(req.dict())
    return {"ok": True, "id": order_id}

@app.api_route("/shipping/orders/{order_id}", methods=["PUT", "POST"])
def update_shipping_order(order_id: int, req: ShippingOrderUpdate):
    fields = {k: v for k, v in req.dict().items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    db.update_shipping_order(order_id, fields)
    return {"ok": True}

@app.get("/shipping/orders")
def list_shipping_orders(status: str = "", limit: int = 50):
    orders = db.get_shipping_orders(status or None, limit)
    return {"ok": True, "data": orders}

@app.get("/shipping/orders/{order_id}")
def get_shipping_order(order_id: int):
    order = db.get_shipping_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    note = build_pdd_order_note(order)
    return {"ok": True, "data": order, "pdd_note": note}

@app.get("/shipping/statuses")
def list_statuses():
    return {"ok": True, "data": SHIPPING_STATUSES}


# ── 仪表盘 ──
@app.get("/dashboard/stats")
def dashboard_stats(days: int = 30):
    data = build_dashboard_data(db, days)
    return {"ok": True, "data": data}


# ── 流量分析 ──
class TrafficRecordCreate(BaseModel):
    draft_id: Optional[int] = None
    product_family_id: Optional[str] = None
    xianyu_item_id: str
    date: str
    title: str = ""
    exposure_count: int = 0
    view_count: int = 0
    want_count: int = 0
    chat_count: int = 0
    order_count: int = 0

@app.post("/traffic/records")
def create_traffic_record(req: TrafficRecordCreate):
    data = req.dict()
    views = data.get("view_count", 1)
    data["conversion_rate"] = round(data.get("order_count", 0) / max(views, 1), 4)
    db.save_traffic_record(data)
    return {"ok": True}

@app.get("/traffic/records")
def list_traffic_records(xianyu_item_id: str = "", date_from: str = "", date_to: str = "", limit: int = 200):
    records = db.get_traffic_records(xianyu_item_id or None, date_from or None, date_to or None, limit)
    return {"ok": True, "data": records}

@app.get("/traffic/items")
def list_traffic_items():
    items = db.get_traffic_items()
    return {"ok": True, "data": items}

@app.post("/traffic/import-csv")
async def import_traffic_csv(file: UploadFile = File(...)):
    import csv
    import io
    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    required = {"date", "xianyu_item_id"}
    if not required.issubset(set(reader.fieldnames or [])):
        raise HTTPException(status_code=400, detail="CSV缺少必要字段: date, xianyu_item_id")
    imported = 0
    errors = []
    for i, row in enumerate(reader, 2):
        try:
            rec = {
                "draft_id": int(row.get("draft_id", 0)) or None,
                "product_family_id": row.get("product_family_id", ""),
                "xianyu_item_id": row["xianyu_item_id"],
                "date": row["date"],
                "title": row.get("title", ""),
                "exposure_count": int(row.get("exposure_count", 0)),
                "view_count": int(row.get("view_count", 0)),
                "want_count": int(row.get("want_count", 0)),
                "chat_count": int(row.get("chat_count", 0)),
                "order_count": int(row.get("order_count", 0)),
            }
            views = rec["view_count"] or 1
            rec["conversion_rate"] = round(rec["order_count"] / max(views, 1), 4)
            db.save_traffic_record(rec)
            imported += 1
        except Exception as e:
            errors.append(f"第{i}行: {e}")
    return {"ok": True, "imported": imported, "errors": errors}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
