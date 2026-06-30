"""
墨禾陶瓷批发系统 — 生产部署版
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
_user_sessions: dict[str, tuple] = {}  # token -> (user_id, expiry)

# ============================================
# APP
# ============================================
app = FastAPI(title="墨禾陶瓷批发", version="2.1")

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
                created_at REAL, customer_name TEXT DEFAULT '',
                customer_phone TEXT DEFAULT '', customer_address TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT, menu_item_id TEXT, item_name TEXT,
                base_price REAL, quantity INTEGER DEFAULT 1,
                temperature TEXT DEFAULT '正常冰',
                sweetness TEXT DEFAULT '标准糖',
                toppings TEXT DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS option_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_key TEXT NOT NULL,
                name TEXT NOT NULL,
                price REAL DEFAULT 0,
                product_id TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY, phone TEXT UNIQUE NOT NULL,
                name TEXT DEFAULT '', created_at REAL
            );
            CREATE TABLE IF NOT EXISTS favorites (
                user_id TEXT, item_id TEXT,
                PRIMARY KEY (user_id, item_id)
            );
            CREATE TABLE IF NOT EXISTS user_addresses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT, name TEXT, phone TEXT,
                province TEXT DEFAULT '', city TEXT DEFAULT '',
                district TEXT DEFAULT '', detail TEXT DEFAULT '',
                is_default INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT DEFAULT ''
            );
        """)
        # Migration
        cols = [r[1] for r in db.execute("PRAGMA table_info(menu_items)").fetchall()]
        if "image_url" not in cols:
            db.execute("ALTER TABLE menu_items ADD COLUMN image_url TEXT DEFAULT ''")
        # Add product_id to option_items
        opt_cols = [r[1] for r in db.execute("PRAGMA table_info(option_items)").fetchall()]
        if "product_id" not in opt_cols:
            db.execute("ALTER TABLE option_items ADD COLUMN product_id TEXT DEFAULT ''")


def seed_menu():
    with get_db() as db:
        if db.execute("SELECT COUNT(*) FROM menu_categories").fetchone()[0] > 0:
            return
        db.executemany("INSERT INTO menu_categories VALUES (?,?,?)", [
            ("hot", "🔥 热销推荐", 1), ("tableware", "🍽️ 餐具系列", 2),
            ("teaset", "🍵 茶具系列", 3), ("vase", "🏺 花瓶摆件", 4),
            ("custom", "🎨 手工定制", 5),
        ])
        db.executemany(
            "INSERT INTO menu_items (id,category_id,name,description,price,image_url,badge,sort_order) VALUES (?,?,?,?,?,?,?,?)",
            [
                ("h1","hot","青花瓷碗套装","6只装·手工绘制·釉下彩·微波炉适用",68,"","hot",1),
                ("h2","hot","手工拉坯茶壶","原矿陶泥·手工拉坯·容量300ml·柴烧工艺",120,"","hot",2),
                ("h3","hot","景德镇白瓷花瓶","高白泥·1320°C高温烧制·高25cm",85,"","hot",3),
                ("h4","hot","日式简约餐具套装","4碗4盘4筷架·釉下彩·洗碗机适用",158,"","new",4),
                ("h5","hot","手绘陶瓷咖啡杯","350ml·手工绘制·每只独一无二",45,"","hot",5),
                ("t1","tableware","陶瓷餐盘套装","4只装·直径22cm·釉下彩·可进微波炉",72,"","",1),
                ("t2","tableware","釉下彩饭碗","单只·直径12cm·高温烧制·安全无毒",28,"","",2),
                ("t3","tableware","陶瓷汤碗大号","直径20cm·双耳设计·可进烤箱",38,"","",3),
                ("t4","tableware","日式拉面碗","直径18cm·复古釉面·经典和风",42,"","new",4),
                ("s1","teaset","功夫茶具套装","一壶四杯一公道·宜兴紫砂·礼盒装",198,"","hot",1),
                ("s2","teaset","汝窑茶杯套装","4只装·天青釉·开片可养·50ml",88,"","",2),
                ("s3","teaset","紫砂茶宠摆件","手工雕刻·原矿紫砂·茶汤滋养变色",55,"","",3),
                ("s4","teaset","旅行茶具便携装","一壶两杯·收纳包·户外功夫茶",128,"","new",4),
                ("v1","vase","北欧风陶瓷花瓶","磨砂白·高30cm·简约百搭",65,"","",1),
                ("v2","vase","手绘青花花瓶","景德镇手工·高35cm·收藏级",180,"","hot",2),
                ("v3","vase","迷你多肉花盆","口径8cm·底部开孔·6色可选",22,"","new",3),
                ("c1","custom","定制Logo陶瓷杯","350ml·丝印/激光雕刻·50只起定",36,"","",1),
                ("c2","custom","企业礼品套装","定制礼盒·含杯+盘+茶叶罐·100套起",260,"","",2),
                ("c3","custom","手工定制茶具","一对一设计·大师手作·收藏证书",350,"","hot",3),
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
    quantity: int = 1; temperature: str = "中号"
    sweetness: str = "白釉"; toppings: list[str] = []

class CreateOrder(BaseModel):
    items: list[OrderItem]
    customer_name: str = ""
    customer_phone: str = ""
    customer_address: str = ""

class MenuUpdate(BaseModel):
    name: Optional[str] = None; description: Optional[str] = None
    price: Optional[float] = None; badge: Optional[str] = None
    is_available: Optional[bool] = None; category_id: Optional[str] = None

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


def seed_options():
    with get_db() as db:
        if db.execute("SELECT COUNT(*) FROM option_items").fetchone()[0] > 0:
            return
        for n in ["小号","中号","大号","特大号"]:
            db.execute("INSERT INTO option_items (group_key,name,price) VALUES ('temperature',?,0)",(n,))
        for n in ["白釉","青釉","天青釉","窑变釉","哑光黑釉"]:
            db.execute("INSERT INTO option_items (group_key,name,price) VALUES ('sweetness',?,0)",(n,))
        for n,p in [("礼盒包装",10),("烫金Logo",15),("定制贺卡",5),("防震包装",8),("加急制作",20),("大师签名",50)]:
            db.execute("INSERT INTO option_items (group_key,name,price) VALUES ('toppings',?,?)",(n,p))


@app.get("/api/options")
def get_options(item_id: str = None):
    with get_db() as db:
        rows = db.execute(
            "SELECT group_key,name,price FROM option_items WHERE product_id=? OR (product_id='' AND NOT EXISTS (SELECT 1 FROM option_items o2 WHERE o2.group_key=option_items.group_key AND o2.product_id=?)) ORDER BY id",
            (item_id or '', item_id or '')
        ).fetchall() if item_id else db.execute("SELECT group_key,name,price FROM option_items WHERE product_id='' ORDER BY id").fetchall()
    result = {"temperature":[],"sweetness":[],"toppings":[]}
    for r in rows:
        if r["group_key"] == "toppings":
            result["toppings"].append({"name":r["name"],"price":r["price"]})
        else:
            result[r["group_key"]].append(r["name"])
    return result


@app.post("/api/orders")
def create_order(req: CreateOrder):
    if not req.items:
        raise HTTPException(400, "订单不能为空")
    oid = str(uuid.uuid4())[:8]
    ono = f"#{int(time.time()) % 100000:05d}"
    tp = {"礼盒包装":10,"烫金Logo":15,"定制贺卡":5,"防震包装":8,"加急制作":20,"大师签名":50}
    total = sum((it.base_price + sum(tp.get(t,0) for t in it.toppings)) * it.quantity for it in req.items)

    with get_db() as db:
        db.execute("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?)", (oid, ono, "pending", round(total,2), time.time(), req.customer_name, req.customer_phone, req.customer_address))
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
        result = []
        for r in db.execute(q, p).fetchall():
            items = db.execute("SELECT * FROM order_items WHERE order_id=?",(r["id"],)).fetchall()
            result.append({
                "id":r["id"],"order_no":r["order_no"],"status":r["status"],
                "total_price":r["total_price"],
                "created_at":time.strftime("%Y-%m-%d %H:%M:%S",time.localtime(r["created_at"])),
                "customer_name":r["customer_name"] or "",
                "customer_phone":r["customer_phone"] or "",
                "customer_address":r["customer_address"] or "",
                "items":[{"name":i["item_name"],"qty":i["quantity"],"price":i["base_price"],"temperature":i["temperature"],"sweetness":i["sweetness"],"toppings":json.loads(i["toppings"])} for i in items],
                "item_count":sum(i["quantity"] for i in items)
            })
        return result


class OrderStatusUpdate(BaseModel):
    status: str

@app.put("/api/admin/orders/{order_id}/status")
def update_order_status(order_id: str, req: OrderStatusUpdate, _=Depends(check_admin)):
    valid = {"pending","paid","shipped","completed","cancelled"}
    if req.status not in valid: raise HTTPException(400, f"无效状态, 可选: {valid}")
    with get_db() as db:
        db.execute("UPDATE orders SET status=? WHERE id=?",(req.status,order_id))
    return {"ok": True}


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
            raise HTTPException(404, "产品不存在")
        fields = {}
        if update.name is not None: fields["name"] = update.name
        if update.description is not None: fields["description"] = update.description
        if update.price is not None:
            if update.price < 0: raise HTTPException(400, "价格不能为负")
            fields["price"] = update.price
        if update.badge is not None: fields["badge"] = update.badge
        if update.is_available is not None: fields["is_available"] = 1 if update.is_available else 0
        if update.category_id is not None: fields["category_id"] = update.category_id
        if not fields: raise HTTPException(400, "没有要更新的字段")
        sets = ", ".join(f"{k}=?" for k in fields)
        db.execute(f"UPDATE menu_items SET {sets} WHERE id=?", list(fields.values())+[item_id])
    return {"ok": True, "updated": fields}


@app.put("/api/admin/menu-items/{item_id}/image")
def update_item_image(item_id: str, image_url: str = "", _=Depends(check_admin)):
    with get_db() as db:
        if not db.execute("SELECT id FROM menu_items WHERE id=?",(item_id,)).fetchone():
            raise HTTPException(404, "产品不存在")
        db.execute("UPDATE menu_items SET image_url=? WHERE id=?",(image_url,item_id))
    return {"ok": True}


@app.delete("/api/admin/menu-items/{item_id}")
def delete_item(item_id: str, _=Depends(check_admin)):
    with get_db() as db:
        if not db.execute("SELECT id FROM menu_items WHERE id=?",(item_id,)).fetchone():
            raise HTTPException(404, "产品不存在")
        db.execute("DELETE FROM menu_items WHERE id=?",(item_id,))
    return {"ok": True}


class CreateItem(BaseModel):
    id: str; name: str; category_id: str = "hot"
    description: str = ""; price: float = 0; badge: str = ""


@app.post("/api/admin/menu-items")
def create_item(req: CreateItem, _=Depends(check_admin)):
    with get_db() as db:
        if db.execute("SELECT id FROM menu_items WHERE id=?",(req.id,)).fetchone():
            raise HTTPException(400, "产品ID已存在")
        db.execute(
            "INSERT INTO menu_items (id,category_id,name,description,price,image_url,badge,sort_order) VALUES (?,?,?,?,?,?,?,99)",
            (req.id, req.category_id, req.name, req.description, req.price, "", req.badge)
        )
    return {"ok": True, "id": req.id}




class CategoryUpdate(BaseModel):
    name: str

@app.get("/api/admin/categories")
def list_categories(_=Depends(check_admin)):
    with get_db() as db:
        cats = db.execute("SELECT id,name,sort_order FROM menu_categories ORDER BY sort_order").fetchall()
    return {"categories": [{"id":c["id"],"name":c["name"],"sort_order":c["sort_order"]} for c in cats]}

@app.put("/api/admin/categories/{cat_id}")
def update_category(cat_id: str, req: CategoryUpdate, _=Depends(check_admin)):
    with get_db() as db:
        if not db.execute("SELECT id FROM menu_categories WHERE id=?",(cat_id,)).fetchone():
            raise HTTPException(404, "分类不存在")
        db.execute("UPDATE menu_categories SET name=? WHERE id=?",(req.name,cat_id))
    return {"ok": True}

@app.delete("/api/admin/categories/{cat_id}")
def delete_category(cat_id: str, _=Depends(check_admin)):
    with get_db() as db:
        if not db.execute("SELECT id FROM menu_categories WHERE id=?",(cat_id,)).fetchone():
            raise HTTPException(404, "分类不存在")
        db.execute("DELETE FROM menu_items WHERE category_id=?",(cat_id,))
        db.execute("DELETE FROM menu_categories WHERE id=?",(cat_id,))
    return {"ok": True}

@app.post("/api/admin/categories")
def create_category(req: CategoryUpdate, _=Depends(check_admin)):
    cat_id = "cat_" + uuid.uuid4().hex[:6]
    with get_db() as db:
        db.execute("INSERT INTO menu_categories (id,name,sort_order) VALUES (?,?,99)",(cat_id,req.name))
    return {"ok": True, "id": cat_id}


# Option management
class OptionUpdate(BaseModel):
    name: str
    price: float = 0
    product_id: str = ""

@app.get("/api/admin/options")
def admin_get_options(product_id: str = "", _=Depends(check_admin)):
    with get_db() as db:
        q = "SELECT id,group_key,name,price,product_id FROM option_items"
        p = []
        if product_id:
            q += " WHERE product_id=?"
            p.append(product_id)
        q += " ORDER BY group_key,id"
        rows = db.execute(q, p).fetchall()
    return {"options": [{"id":r["id"],"group_key":r["group_key"],"name":r["name"],"price":r["price"],"product_id":r["product_id"]} for r in rows]}

@app.put("/api/admin/options/{opt_id}")
def update_option(opt_id: int, req: OptionUpdate, _=Depends(check_admin)):
    with get_db() as db:
        db.execute("UPDATE option_items SET name=?,price=? WHERE id=?",(req.name,req.price,opt_id))
    return {"ok": True}

@app.delete("/api/admin/options/{opt_id}")
def delete_option(opt_id: int, _=Depends(check_admin)):
    with get_db() as db:
        db.execute("DELETE FROM option_items WHERE id=?",(opt_id,))
    return {"ok": True}

@app.post("/api/admin/options")
def create_option(req: OptionUpdate, group_key: str = "temperature", _=Depends(check_admin)):
    with get_db() as db:
        db.execute("INSERT INTO option_items (group_key,name,price,product_id) VALUES (?,?,?,?)",(group_key,req.name,req.price,req.product_id))
    return {"ok": True}


# Payment config
def get_config(key, default=""):
    with get_db() as db:
        r = db.execute("SELECT value FROM config WHERE key=?",(key,)).fetchone()
    return r["value"] if r else default

@app.get("/api/payment")
def get_payment():
    return {
        "alipay": get_config("alipay_url"),
        "wechat": get_config("wechat_url"),
        "phone": get_config("contact_phone", ""),
        "banner": get_config("banner_url", ""),
        "address": get_config("contact_address", "景德镇市珠山区")
    }

@app.get("/api/admin/config")
def admin_get_config(_=Depends(check_admin)):
    rows = {}
    with get_db() as db:
        for r in db.execute("SELECT key,value FROM config").fetchall():
            rows[r["key"]] = r["value"]
    return rows

class ConfigUpdate(BaseModel):
    key: str
    value: str = ""

@app.put("/api/admin/config")
def admin_set_config(req: ConfigUpdate, _=Depends(check_admin)):
    with get_db() as db:
        db.execute("INSERT OR REPLACE INTO config (key,value) VALUES (?,?)",(req.key,req.value))
    return {"ok": True}


# ============================================
# USER API
# ============================================
class UserLoginReq(BaseModel):
    phone: str
    name: str = ""

@app.post("/api/user/login")
def user_login(req: UserLoginReq):
    if not req.phone:
        raise HTTPException(400, "手机号不能为空")
    with get_db() as db:
        u = db.execute("SELECT * FROM users WHERE phone=?", (req.phone,)).fetchone()
        if not u:
            uid = uuid.uuid4().hex[:12]
            db.execute("INSERT INTO users (id,phone,name,created_at) VALUES (?,?,?,?)",
                       (uid, req.phone, req.name or "用户" + req.phone[-4:], time.time()))
        else:
            uid = u["id"]
    token = secrets.token_hex(32)
    _user_sessions[token] = (uid, time.time())
    return {"token": token, "user": {"id": uid, "phone": req.phone, "name": req.name or "用户" + req.phone[-4:]}}


def get_current_user(authorization=Header(None)):
    if not authorization:
        raise HTTPException(401, "请先登录")
    token = authorization.replace("Bearer ", "")
    if token not in _user_sessions:
        raise HTTPException(401, "登录已过期")
    uid, ts = _user_sessions[token]
    if time.time() - ts > 86400 * 7:
        del _user_sessions[token]
        raise HTTPException(401, "登录已过期")
    return uid


@app.get("/api/user/info")
def user_info(uid=Depends(get_current_user)):
    with get_db() as db:
        u = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    return {"id": u["id"], "phone": u["phone"], "name": u["name"]}


# Favorites
@app.get("/api/user/favorites")
def list_favorites(uid=Depends(get_current_user)):
    with get_db() as db:
        fvs = db.execute("SELECT item_id FROM favorites WHERE user_id=?", (uid,)).fetchall()
        items = []
        for fv in fvs:
            it = db.execute("SELECT * FROM menu_items WHERE id=? AND is_available=1", (fv["item_id"],)).fetchone()
            if it:
                items.append({"item_id": it["id"], "category_id": it["category_id"], "item_name": it["name"], "price": it["price"], "image_url": it["image_url"] or ""})
    return items


@app.post("/api/user/favorites/{item_id}")
def add_favorite(item_id: str, uid=Depends(get_current_user)):
    with get_db() as db:
        db.execute("INSERT OR IGNORE INTO favorites (user_id,item_id) VALUES (?,?)", (uid, item_id))
    return {"ok": True}


@app.delete("/api/user/favorites/{item_id}")
def remove_favorite(item_id: str, uid=Depends(get_current_user)):
    with get_db() as db:
        db.execute("DELETE FROM favorites WHERE user_id=? AND item_id=?", (uid, item_id))
    return {"ok": True}


# Addresses
@app.get("/api/user/addresses")
def list_addresses(uid=Depends(get_current_user)):
    with get_db() as db:
        rows = db.execute("SELECT * FROM user_addresses WHERE user_id=? ORDER BY is_default DESC,id DESC", (uid,)).fetchall()
    return [{"id": r["id"], "name": r["name"], "phone": r["phone"],
                               "address": r["province"] or "", "detail": r["detail"] or "",
                               "is_default": r["is_default"]} for r in rows]


class AddressUpdate(BaseModel):
    name: str
    phone: str
    address: str = ""
    detail: str = ""
    is_default: int = 0


@app.post("/api/user/addresses")
def create_address(req: AddressUpdate, uid=Depends(get_current_user)):
    with get_db() as db:
        if req.is_default:
            db.execute("UPDATE user_addresses SET is_default=0 WHERE user_id=?", (uid,))
        c = db.execute(
            "INSERT INTO user_addresses (user_id,name,phone,province,detail,is_default) VALUES (?,?,?,?,?,?)",
            (uid, req.name, req.phone, req.address, req.detail, req.is_default))
    return {"ok": True, "id": c.lastrowid}


@app.put("/api/user/addresses/{addr_id}")
def update_address(addr_id: int, req: AddressUpdate, uid=Depends(get_current_user)):
    with get_db() as db:
        if req.is_default:
            db.execute("UPDATE user_addresses SET is_default=0 WHERE user_id=?", (uid,))
        db.execute(
            "UPDATE user_addresses SET name=?,phone=?,province=?,detail=?,is_default=? WHERE id=? AND user_id=?",
            (req.name, req.phone, req.address, req.detail, req.is_default, addr_id, uid))
    return {"ok": True}


@app.delete("/api/user/addresses/{addr_id}")
def delete_address(addr_id: int, uid=Depends(get_current_user)):
    with get_db() as db:
        db.execute("DELETE FROM user_addresses WHERE id=? AND user_id=?", (addr_id, uid))
    return {"ok": True}


# User orders (filtered by user_id, with status filter)
@app.get("/api/user/orders")
def user_orders(status: str = "", uid=Depends(get_current_user)):
    with get_db() as db:
        q = "SELECT * FROM orders WHERE customer_phone=(SELECT phone FROM users WHERE id=?)"
        p = [uid]
        if status:
            q += " AND status=?"
            p.append(status)
        q += " ORDER BY created_at DESC LIMIT 50"
        result = []
        for r in db.execute(q, p).fetchall():
            items = db.execute("SELECT * FROM order_items WHERE order_id=?", (r["id"],)).fetchall()
            result.append({
                "id": r["id"], "order_no": r["order_no"], "status": r["status"], "total_price": r["total_price"],
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["created_at"])),
                "items": [{"name": i["item_name"], "qty": i["quantity"], "price": i["base_price"]} for i in items],
                "item_count": sum(i["quantity"] for i in items)
            })
        return result


@app.get("/api/health")
def health():
    return {"status":"ok","service":"墨禾陶瓷批发"}


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
    seed_options()
    print(f"🏺 墨禾陶瓷批发 v2.1 已启动")
    print(f"   地址: http://0.0.0.0:{PORT}")
    print(f"   管理密码: {ADMIN_PASSWORD}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)

