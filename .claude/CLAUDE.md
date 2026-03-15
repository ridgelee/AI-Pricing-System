# AI Pricing System — 开发者指南

## 项目简介

本项目从 `careplan-mvp`（CVS Specialty Pharmacy Care Plan 自动生成系统）改造而来，是一个面向综合零售商的 **AI 智能定价系统**。定价分析师通过批量上传 SKU CSV 文件，系统从内部商品数据库（知识库 Agent + pgvector 向量检索）获取商品上下文，调用 Claude API 生成包含建议价格、价格区间和定价依据的 JSON 报告，最终以 CSV 格式下载。

**项目性质**：Demo 展示项目，不需要生产级安全/性能要求。

---

## 技术栈

| 组件 | 状态 | 版本/说明 |
|------|------|-----------|
| Django + DRF | **复用** | 4.2，后端框架不变 |
| React + Vite | **改造** | 18 / 5，表单改为 CSV 上传界面 |
| PostgreSQL | **改造** | 换用 `pgvector/pgvector:pg15` 镜像，支持向量列 |
| Celery + Redis | **复用** | 5.3.6，异步批量处理 SKU |
| Anthropic Claude API | **复用** | claude-sonnet-4，Prompt 重写为定价分析师角色 |
| Docker Compose | **微调** | postgres 服务换镜像，其余服务不变 |
| 统一异常处理 | **直接复用** | `exceptions.py`, `exception_handler.py` 无需修改 |
| pytest | **改造** | conftest.py 结构复用，测试用例重写 |
| pgvector | **新增** | PostgreSQL 向量扩展，`vector(384)` 列 |
| sentence-transformers | **新增** | `all-MiniLM-L6-v2`，本地加载，无需 API Key，384 维向量 |

---

## 目录结构

```
AI-Pricing-System/
├── .claude/
│   └── CLAUDE.md                   # 本文件
├── docs/
│   └── PRD.md                      # 产品需求文档
└── careplan-mvp/                   # 主项目目录（从 careplan-mvp 改造）
    ├── docker-compose.yml
    ├── backend/
    │   ├── config/
    │   │   ├── settings.py         # 新增 pgvector、sentence-transformers 配置
    │   │   ├── celery.py           # 不变
    │   │   └── urls.py             # 路由从 careplan/ 改为 pricing/
    │   ├── pricing/                # 原 careplan/ 改名
    │   │   ├── models.py           # Product, PricingRequest, PricingResult
    │   │   ├── agents.py           # ★ 新增：KnowledgeBaseAgent
    │   │   ├── services.py         # 重写：build_pricing_prompt(), call_llm()
    │   │   ├── tasks.py            # 改造：generate_pricing()
    │   │   ├── views.py            # 重写：CSV上传、进度查询、CSV下载
    │   │   ├── serializers.py      # 重写
    │   │   ├── urls.py             # 重写：/api/pricing/ 路由
    │   │   ├── exceptions.py       # ✅ 直接复用
    │   │   ├── exception_handler.py # ✅ 直接复用
    │   │   ├── migrations/         # 全部删除重建
    │   │   └── management/
    │   │       └── commands/
    │   │           └── load_sku_data.py  # ★ 新增：导入示例 SKU 数据
    │   └── tests/
    │       ├── conftest.py         # 更新 fixtures
    │       ├── unit/               # 重写
    │       └── integration/        # 重写
    └── frontend/
        └── src/
            └── App.jsx             # 全部重写：CSV上传 + 结果表格 + CSV下载
```

---

## 编码规范

### 命名约定
- **Django App**：`pricing`（原 `careplan`）
- **模型命名**：`Product`、`PricingRequest`、`PricingResult`
- **API 路径前缀**：`/api/pricing/`（原 `/api/orders/`）
- **Celery 任务**：`generate_pricing`（原 `generate_care_plan`）
- **Python**：snake_case 变量/函数，PascalCase 类名
- **React**：camelCase 变量，PascalCase 组件

### 文件组织原则
- 业务逻辑放在 `services.py`，知识库检索逻辑放在 `agents.py`
- 不在 `views.py` 中直接调用 LLM，通过 Celery 任务异步处理
- `exceptions.py` 中的自定义异常类保持不变，直接继承复用

### 禁止事项
- 不在 `views.py` 中写业务逻辑（放 `services.py`）
- 不在同步视图中调用 LLM API（走 Celery 异步）
- 不删除 `exceptions.py` 和 `exception_handler.py`（直接复用）
- 不在前端存储定价结果（通过 API 下载）

---

## 架构决策

### 1. pgvector + PostgreSQL（向量检索）
**决策**：在现有 PostgreSQL 基础上加 pgvector 扩展，而非引入独立向量数据库（Chroma/Pinecone）。
**原因**：Demo 场景 SKU 数量有限，pgvector 完全够用；减少基础设施复杂度，不增加新服务。

### 2. sentence-transformers 本地运行
**决策**：使用 `all-MiniLM-L6-v2` 本地加载，不调用外部 Embedding API。
**原因**：Demo 项目无需调用外部 API；本地运行保证确定性，避免网络依赖；模型约 80MB，首次 Docker 构建时下载。

### 3. 知识库 Agent 检索策略
**决策**：优先精确匹配（SKU ID 直查），fallback 到向量相似度搜索。
**原因**：用户上传的 SKU ID 若在数据库中存在，精确匹配最可靠；向量搜索处理拼写变体或相似商品查询。

### 4. 批量异步处理
**决策**：复用 Celery 异步架构，一个 PricingRequest 对应多个 PricingResult。
**原因**：与原 Order→CarePlan 一对一关系不同，一次 CSV 上传包含多个 SKU，需要一对多。PricingResult 用 ForeignKey（而非原来的 OneToOne）关联 PricingRequest。

### 5. LLM 输出格式
**决策**：要求 LLM 返回结构化 JSON，后端解析后存入独立字段。
**原因**：方便程序处理和 CSV 导出，不依赖前端解析；和原 CarePlan 纯文本输出不同。

---

## 从 careplan-mvp 迁移注意事项

### 模型映射
| 旧模型 | 新模型 | 操作 |
|--------|--------|------|
| `Patient` | — | **删除** |
| `Provider` | — | **删除** |
| `Order` | `PricingRequest` | 字段完全重写 |
| `CarePlan` | `PricingResult` | OneToOne → ForeignKey，字段重写 |
| — | `Product` | 新建 |

### 需要删除的旧代码
- `careplan/models.py` 中的 `Patient`, `Provider` 类
- `careplan/services.py` 中的 `check_provider_duplicate()`, `check_patient_duplicate()`, `check_order_duplicate()`, `build_prompt()`（Care Plan 版本）
- `careplan/migrations/` 下所有迁移文件（重建）
- 前端 `App.jsx` 中所有表单字段（患者/医生信息）

### 直接复用（无需修改）
- `careplan/exceptions.py` → 改名 `pricing/exceptions.py`，内容不变
- `careplan/exception_handler.py` → 改名 `pricing/exception_handler.py`，内容不变
- `config/celery.py` — 不变
- `config/settings.py` 中的 DB、Redis、CORS 配置 — 不变，仅新增 pgvector 初始化

### URL 路由变更
```python
# 旧
path('api/', include('careplan.urls'))

# 新
path('api/', include('pricing.urls'))
```

---

## 常用命令

```bash
# 启动全栈（含数据库、Redis、Celery、前端）
docker-compose up

# 首次启动后导入示例 SKU 数据（含向量嵌入）
docker-compose exec backend python manage.py load_sku_data

# 数据库迁移
docker-compose exec backend python manage.py makemigrations pricing
docker-compose exec backend python manage.py migrate

# 运行测试
docker-compose run --rm test

# 进入后端容器 shell
docker-compose exec backend bash

# 查看 Celery 任务监控
open http://localhost:5555  # Flower UI

# 重建镜像（修改 requirements.txt 后）
docker-compose build backend
```

---

## 环境变量

项目根目录下创建 `.env` 文件：

```env
# 数据库
DATABASE_URL=postgresql://postgres:postgres@db:5432/pricing_db

# Redis
REDIS_URL=redis://redis:6379/0

# Anthropic API
ANTHROPIC_API_KEY=sk-ant-...

# Django
SECRET_KEY=your-secret-key
DEBUG=True
```
