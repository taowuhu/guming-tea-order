# 🍵 古茗风格点单小程序 — 交付文档

## 项目概述

仿古茗奶茶风格的点单系统，包含手机端点单前端 + 管理后台。

| 模块 | 说明 |
|------|------|
| 点单页面 | 5大分类 19款饮品，定制温度/甜度/加料，购物车下单 |
| 管理后台 | 上传饮品图片、修改价格/名称/描述、上下架管理、订单查询 |
| 后端 API | FastAPI + SQLite，6个客户端接口 + 5个管理端接口 |

## 快速启动（3种方式）

### 方式一：Docker（推荐，一条命令）

```bash
# 1. 进入项目目录
cd guming-tea-order

# 2. 修改管理密码
# 编辑 docker-compose.yml，把 ADMIN_PASSWORD 改成你自己的密码

# 3. 启动
docker-compose up -d

# 4. 访问
#    http://你的服务器IP:8000      → 点单页面
#    http://你的服务器IP:8000      → 连点5次品牌名进入管理后台
```

### 方式二：直接运行（需 Python 3.11+）

```bash
# 1. 进入项目目录
cd guming-tea-order

# 2. 安装依赖
uv venv
uv pip install fastapi uvicorn

# 3. 修改密码
# Windows: set ADMIN_PASSWORD=你的密码
# Linux/Mac: export ADMIN_PASSWORD=你的密码

# 4. 启动
.venv/Scripts/python backend/main.py    # Windows
.venv/bin/python backend/main.py        # Linux/Mac
```

### 方式三：部署到云平台

#### Railway / Render（海外）
1. 推送代码到 GitHub
2. 在 Railway/Render 中导入仓库
3. 设置环境变量 `ADMIN_PASSWORD=你的密码`
4. 自动部署

#### 阿里云 / 腾讯云（国内）
1. 购买轻量应用服务器（最低 2核2G，约 ¥60/月）
2. 安装 Docker：`curl -fsSL https://get.docker.com | bash`
3. 上传项目文件
4. 运行 `docker-compose up -d`
5. 配置域名 + SSL 证书（可选）

## 管理后台使用

### 进入方式
- **手机端**：连续快速点击 5 次顶部"古茗·点单"品牌名
- **电脑端**：页面加载 3 秒后右上角会出现 ⚙️ 齿轮图标

### 首次登录
默认密码：`guming2024`（⚠️ 上线前务必修改）

### 管理功能

| 操作 | 方法 |
|------|------|
| 改名称/价格/描述 | 直接编辑 → 点 💾 保存 |
| 换角标 | 下拉选 无/🔥热卖/🆕上新 → 保存 |
| 上传图片 | 点 📷 换图 → 选文件 → 确认上传 |
| 上架/下架 | 点 👁 按钮切换（下架的饮品顾客看不到） |

### 修改密码
编辑 `docker-compose.yml` 中的 `ADMIN_PASSWORD` 或设置系统环境变量，重启服务生效。

## API 接口

### 客户端接口（无需登录）
| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/menu` | GET | 获取菜单 |
| `/api/options` | GET | 获取定制选项 |
| `/api/orders` | POST | 提交订单 |
| `/api/orders` | GET | 查询订单列表 |
| `/api/orders/{id}` | GET | 订单详情 |
| `/api/health` | GET | 健康检查 |

### 管理端接口（需登录）
| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/admin/login` | POST | 管理登录 |
| `/api/admin/upload-image` | POST | 上传图片 |
| `/api/admin/menu-items` | GET | 菜单管理列表 |
| `/api/admin/menu-items/{id}` | PUT | 更新饮品信息 |
| `/api/admin/menu-items/{id}/image` | PUT | 更新饮品图片 |

## 文件结构

```
guming-tea-order/
├── backend/
│   ├── main.py           # FastAPI 后端
│   ├── requirements.txt  # Python 依赖
│   ├── data.db           # SQLite 数据库（自动生成）
│   └── uploads/          # 上传的图片（自动生成）
├── frontend/
│   └── index.html        # 前端（单文件，含 CSS/JS）
├── docker-compose.yml    # Docker 编排
├── Dockerfile            # Docker 镜像
├── .env.example          # 环境变量模板
├── start.bat             # Windows 快速启动
└── README.md             # 本文档
```

## 常见问题

**Q: 数据存在哪里？**
A: SQLite 数据库 `backend/data.db`，Docker 部署时挂载到 `./data/` 目录，持久化保存。

**Q: 图片存在哪里？**
A: `backend/uploads/` 目录，Docker 部署时同样挂载持久化。

**Q: 如何备份？**
A: 复制 `data.db` 和 `uploads/` 文件夹即可。

**Q: 忘记管理密码怎么办？**
A: 修改 `ADMIN_PASSWORD` 环境变量后重启服务。

**Q: 日订单量很大 SQLite 够用吗？**
A: SQLite 单文件可支持日均数千单。如需更大规模，可改为 MySQL/PostgreSQL。

## 上线检查清单

- [ ] 修改 `ADMIN_PASSWORD` 为强密码
- [ ] 配置域名（可选）
- [ ] 配置 HTTPS（可选，推荐）
- [ ] 每日备份 `data.db` 和 `uploads/`
- [ ] 测试下单流程
- [ ] 上传饮品的真实图片
- [ ] 确认所有价格正确
