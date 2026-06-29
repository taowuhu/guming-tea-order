"""
古茗风格点单系统 — 生产部署版
一条命令部署：docker-compose up -d
"""
import sqlite3, json, time, uuid, shutil, os, secrets
from pathlib import Path
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

# ============================================
# CONFIG
# ============================================
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "guming2024")
PORT = int(os.getenv("PORT", "8000"))
DB_PATH = Path(__file__).parent / "data.db"
UPLOAD_DIR = Path(__file__).parent / "uploads"
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
UPLOAD_DIR.mkdir(exist_ok=True)

_admin_sessions: dict[str, float] = {}

# ============================================
# APP
# ============================================
app = FastAPI(title="古茗点单系统", version="2.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@contextmanager
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ============================================
# DATABASE
# ============================================
def init_db():
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS menu_categories (
                id TEXT PRIMARY KEY, name TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS menu_items (
                id TEXT PRIMARY KEY, category_id TEXT NOT NULL,
                name TEXT NOT NULL, description TEXT DEFAULT '',
                price REAL NOT NULL, image_url TEXT DEFAULT '',
                badge TEXT DEFAULT '', sort_order INTEGER DEFAULT 0,
                is_available INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY, order_no TEXT UNIQUE,
                status TEXT DEFAULT 'pending', total_price REAL,
                created_at REAL
            );
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT, menu_item_id TEXT, item_name TEXT,
                base_price REAL, quantity INTEGER DEFAULT 1,
                temperature TEXT DEFAULT '正常冰',
                sweetness TEXT DEFAULT '标准糖',
                toppings TEXT DEFAULT '[]'
            );
        """)
        # Migration
        cols = [r[1] for r in db.execute("PRAGMA table_info(menu_items)").fetchall()]
        if "image_url" not in cols:
            db.execute("ALTER TABLE menu_items ADD COLUMN image_url TEXT DEFAULT ''")


def seed_menu():
    with get_db() as db:
        if db.execute("SELECT COUNT(*) FROM menu_categories").fetchone()[0] > 0:
            return
        db.executemany("INSERT INTO menu_categories VALUES (?,?,?)", [
            ("recommend", "🔥 人气推荐", 1), ("fruit", "🍊 轻盈果茶", 2),
            ("milktea", "🧋 醇香奶茶", 3), ("clear", "🥛 清乳茶", 4),
            ("pure", "🍵 鲜萃茗茶", 5),
        ])
        db.executemany(
            "INSERT INTO menu_items (id,category_id,name,description,price,image_url,badge,sort_order) VALUES (?,?,?,?,?,?,?,?)",
            [
                ("r1","recommend","云岭茉莉白","茉莉绿茶底 · 鲜牛乳 · 清甜回甘",13,"","hot",1),
                ("r2","recommend","布蕾脆脆奶芙","焦糖布蕾 · 脆脆珠 · 奶油顶",17,"","hot",2),
                ("r3","recommend","超A芝士葡萄","巨峰葡萄 · 芝士奶盖 · 茉莉茶底",18,"","hot",3),
                ("r4","recommend","杨枝甘露轻盈版","芒果 · 西柚 · 椰奶 · 0脂",16,"","new",4),
                ("r5","recommend","黑桑莓莓","黑桑葚 · 草莓 · 茉莉绿茶",16,"","hot",5),
                ("f1","fruit","满杯鲜柚","西柚片 · 茉莉绿茶 · 维C满满",15,"","",1),
                ("f2","fruit","爆柠四季春","香水柠檬 · 四季春茶 · 手打爆汁",13,"","",2),
                ("f3","fruit","桃气乌龙","蜜桃果肉 · 乌龙茶 · 桃香四溢",14,"","",3),
                ("f4","fruit","西瓜椰椰","海南麒麟瓜 · 椰乳 · 清甜解暑",13,"","new",4),
                ("m1","milktea","招牌奶茶","锡兰红茶 · 牛乳 · Q弹珍珠",12,"","hot",1),
                ("m2","milktea","大红袍奶茶","武夷山大红袍 · 鲜牛乳 · 焦糖风味",15,"","",2),
                ("m3","milktea","桂花酒酿奶茶","桂花酿 · 酒酿糯米 · 奶茶融合",14,"","",3),
                ("m4","milktea","厚芋泥波波","手捣芋泥 · 黑糖波波 · 厚牛乳",16,"","",4),
                ("c1","clear","茉莉奶绿","茉莉花茶 · 鲜牛乳 · 0植脂末",12,"","",1),
                ("c2","clear","栀香清乳","栀子花茶 · 鲜牛乳 · 花香淡雅",13,"","new",2),
                ("c3","clear","白桃清乳","白桃乌龙 · 脱脂牛乳 · 轻盈不腻",14,"","",3),
                ("p1","pure","龙井鲜萃","西湖龙井 · 鲜叶冷萃 · 豆香清冽",18,"","",1),
                ("p2","pure","茉莉飘雪","横县茉莉 · 飘雪工艺 · 七窨花香",14,"","new",2),
                ("p3","pure","桂花乌龙","安溪铁观音 · 金秋桂花 · 岩骨花香",15,"","",3),
            ]
        )


# ============================================
# AUTH
# ============================================
def check_admin(authorization=Header(None)):
    if not authorization:
        raise HTTPException(401, "请先登录管理后台")
    token = authorization.replace("Bearer ", "")
    if token not in _admin_sessions:
        raise HTTPException(401, "Token无效")
    if time.time() - _admin_sessions[token] > 86400:
        del _admin_sessions[token]
        raise HTTPException(401, "Token已过期")


class LoginReq(BaseModel):
    password: str


@app.post("/api/admin/login")
def admin_login(req: LoginReq):
    if req.password != ADMIN_PASSWORD:
        raise HTTPException(403, "密码错误")
    token = secrets.token_hex(32)
    _admin_sessions[token] = time.time()
    return {"token": token}


# ============================================
# MODELS
# ============================================
class OrderItem(BaseModel):
    menu_item_id: str; item_name: str; base_price: float
    quantity: int = 1; temperature: str = "正常冰"
    sweetness: str = "标准糖"; toppings: list[str] = []

class CreateOrder(BaseModel):
    items: list[OrderItem]

class MenuUpdate(BaseModel):
    name: Optional[str] = None; description: Optional[str] = None
    price: Optional[float] = None; badge: Optional[str] = None
    is_available: Optional[bool] = None

# ============================================
# CLIENT API
# ============================================
@app.get("/api/menu")
def get_menu():
    with get_db() as db:
        cats = db.execute("SELECT id,name FROM menu_categories ORDER BY sort_order").fetchall()
        return {"categories": [{
            "id": c["id"], "name": c["name"],
            "items": [{
                "id": i["id"], "name": i["name"], "desc": i["description"],
                "price": i["price"], "image_url": i["image_url"] or "",
                "badge": i["badge"]
            } for i in db.execute(
                "SELECT * FROM menu_items WHERE category_id=? AND is_available=1 ORDER BY sort_order",
                (c["id"],)
            ).fetchall()]
        } for c in cats]}


@app.get("/api/options")
def get_options():
    return {
        "temperature": ["正常冰","少冰","去冰","常温","温","热"],
        "sweetness": ["标准糖","七分糖","五分糖","三分糖","无糖"],
        "toppings": [
            {"name":"珍珠","price":2},{"name":"椰果","price":2},
            {"name":"布丁","price":3},{"name":"仙草","price":2},
            {"name":"芋圆","price":3},{"name":"芝士奶盖","price":4}
        ]
    }


@app.post("/api/orders")
def create_order(req: CreateOrder):
    if not req.items:
        raise HTTPException(400, "订单不能为空")
    oid = str(uuid.uuid4())[:8]
    ono = f"#{int(time.time()) % 100000:05d}"
    tp = {"珍珠":2,"椰果":2,"布丁":3,"仙草":2,"芋圆":3,"芝士奶盖":4}
    total = sum((it.base_price + sum(tp.get(t,0) for t in it.toppings)) * it.quantity for it in req.items)

    with get_db() as db:
        db.execute("INSERT INTO orders VALUES (?,?,?,?,?)", (oid, ono, "pending", round(total,2), time.time()))
        for it in req.items:
            db.execute(
                "INSERT INTO order_items (order_id,menu_item_id,item_name,base_price,quantity,temperature,sweetness,toppings) VALUES (?,?,?,?,?,?,?,?)",
                (oid, it.menu_item_id, it.item_name, it.base_price, it.quantity, it.temperature, it.sweetness, json.dumps(it.toppings))
            )
    return {"id":oid,"order_no":ono,"status":"pending","total_price":round(total,2),
            "item_count":sum(it.quantity for it in req.items),
            "created_at":time.strftime("%Y-%m-%d %H:%M:%S")}


@app.get("/api/orders")
def list_orders(status: Optional[str] = None, limit: int = 50):
    with get_db() as db:
        q = "SELECT * FROM orders"
        p = []
        if status:
            q += " WHERE status=?"
            p.append(status)
        q += " ORDER BY created_at DESC LIMIT ?"
        p.append(limit)
        return [{"id":r["id"],"order_no":r["order_no"],"status":r["status"],
                 "total_price":r["total_price"],
                 "created_at":time.strftime("%Y-%m-%d %H:%M:%S",time.localtime(r["created_at"]))}
                for r in db.execute(q, p).fetchall()]


# ============================================
# ADMIN API
# ============================================
@app.post("/api/admin/upload-image")
async def upload_image(file: UploadFile = File(...), _=Depends(check_admin)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "只允许上传图片")
    ext = Path(file.filename).suffix.lower() or ".jpg"
    if ext not in (".jpg",".jpeg",".png",".gif",".webp",".bmp"):
        raise HTTPException(400, f"不支持的格式: {ext}")
    fname = f"{uuid.uuid4().hex}{ext}"
    with open(UPLOAD_DIR / fname, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"url": f"/uploads/{fname}", "filename": fname}


@app.get("/api/admin/menu-items")
def admin_list_items(_=Depends(check_admin)):
    with get_db() as db:
        items = db.execute(
            "SELECT m.*,c.name as cat_name FROM menu_items m LEFT JOIN menu_categories c ON m.category_id=c.id ORDER BY c.sort_order,m.sort_order"
        ).fetchall()
        cats = db.execute("SELECT id,name FROM menu_categories ORDER BY sort_order").fetchall()
        return {
            "categories": [{"id":c["id"],"name":c["name"]} for c in cats],
            "items": [{"id":i["id"],"category_id":i["category_id"],"name":i["name"],
                       "description":i["description"],"price":i["price"],
                       "image_url":i["image_url"] or "","badge":i["badge"],
                       "sort_order":i["sort_order"],"is_available":bool(i["is_available"]),
                       "cat_name":i["cat_name"]} for i in items]
        }


@app.put("/api/admin/menu-items/{item_id}")
def update_menu_item(item_id: str, update: MenuUpdate, _=Depends(check_admin)):
    with get_db() as db:
        if not db.execute("SELECT id FROM menu_items WHERE id=?",(item_id,)).fetchone():
            raise HTTPException(404, "饮品不存在")
        fields = {}
        if update.name is not None: fields["name"] = update.name
        if update.description is not None: fields["description"] = update.description
        if update.price is not None:
            if update.price < 0: raise HTTPException(400, "价格不能为负")
            fields["price"] = update.price
        if update.badge is not None: fields["badge"] = update.badge
        if update.is_available is not None: fields["is_available"] = 1 if update.is_available else 0
        if not fields: raise HTTPException(400, "没有要更新的字段")
        sets = ", ".join(f"{k}=?" for k in fields)
        db.execute(f"UPDATE menu_items SET {sets} WHERE id=?", list(fields.values())+[item_id])
    return {"ok": True, "updated": fields}


@app.put("/api/admin/menu-items/{item_id}/image")
def update_item_image(item_id: str, image_url: str = "", _=Depends(check_admin)):
    with get_db() as db:
        if not db.execute("SELECT id FROM menu_items WHERE id=?",(item_id,)).fetchone():
            raise HTTPException(404, "饮品不存在")
        db.execute("UPDATE menu_items SET image_url=? WHERE id=?",(image_url,item_id))
    return {"ok": True}


@app.get("/api/health")
def health():
    return {"status":"ok","service":"古茗点单系统"}


# ============================================
# STATIC FILES
# ============================================
@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")

app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


@app.get("/{path:path}")
async def serve_frontend(path: str):
    fp = FRONTEND_DIR / path
    if fp.exists() and fp.is_file():
        return FileResponse(fp)
    return FileResponse(FRONTEND_DIR / "index.html")


# ============================================
# STARTUP
# ============================================
@app.on_event("startup")
def startup():
    init_db()
    seed_menu()
    print(f"🍵 古茗点单系统 v2.1 已启动")
    print(f"   地址: http://0.0.0.0:{PORT}")
    print(f"   管理密码: {ADMIN_PASSWORD}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
