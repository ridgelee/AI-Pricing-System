# AI Pricing System — 产品需求文档（PRD）

**版本**：v1.0
**日期**：2026-03-04
**项目性质**：Demo 展示项目

---

## 1. 产品概述

### 问题
综合零售商管理数千个 SKU，传统人工定价依赖经验和简单的成本加成公式，难以综合考虑商品分类特性、库存状态、历史销售规律等多维度因素，导致定价质量参差不齐，利润率难以最优化。

### 方案
AI 定价系统通过知识库 Agent 自动从内部数据库检索每个 SKU 的完整商品信息（成本、大类细类、库存、历史销量），以结构化上下文驱动大语言模型（Claude）扮演专业定价分析师，输出建议价格、价格区间和定价依据说明。

### 价值
- **效率**：批量处理，一次上传 CSV → 批量获得 AI 定价建议，替代逐个人工分析
- **质量**：LLM 综合多维度因素给出建议价格区间，并提供可审阅的定价依据
- **可追溯**：每次定价请求和结果完整记录，便于回溯和审计

### 改造背景
本系统从 `careplan-mvp`（CVS Specialty Pharmacy Care Plan 自动生成系统）改造而来。核心异步处理架构（Celery + Redis）、LLM 调用链路、状态流转机制（pending→processing→completed→failed）和 Docker Compose 部署架构均直接复用，业务逻辑和数据模型完全重写。

---

## 2. 用户角色

### 定价分析师（唯一角色）

**描述**：负责商品价格管理的内部人员，通过系统批量获取 AI 定价建议并参考制定最终价格。

**能做什么**：
- 上传包含 SKU ID 的 CSV 文件，发起批量定价请求
- 查看定价请求的处理进度
- 查看每个 SKU 的定价建议（建议价、价格区间、预期利润率、定价依据）
- 下载定价结果 CSV 文件，用于进一步分析或汇报

**不需要**：
- 登录/认证（Demo 阶段无需权限管理）
- 手动输入商品详情（系统自动从知识库检索）
- 审批流程（结果供参考，最终定价由分析师决定）

---

## 3. 核心功能模块

### 3.1 CSV 批量上传

**是什么**：用户上传包含 SKU ID 列的 CSV 文件，触发批量定价流程。

**谁用**：定价分析师

**怎么用**：
1. 点击上传区域或拖拽 CSV 文件
2. 系统校验文件格式和必填列（`sku_id`）
3. 上传成功后返回请求 ID，前端进入轮询状态

**CSV 输入格式**：
```csv
sku_id
SKU-001
SKU-002
SKU-003
```

**边界条件**：
- 仅接受 `.csv` 格式文件
- 必须包含 `sku_id` 列（不区分大小写）
- 单次上传 SKU 数量建议不超过 100 条（Demo 限制）
- 文件中的 SKU ID 若在数据库中不存在，系统将通过向量搜索找最近邻，并在结果中标注

### 3.2 知识库检索（Knowledge Base Agent）

**是什么**：后台自动运行的模块，根据 SKU ID 从商品数据库检索完整的商品信息，构建 LLM 所需的上下文。

**触发时机**：Celery 任务处理每个 SKU 时自动调用，用户不可见。

**检索流程**：
1. 精确匹配：用 `sku_id` 直接查询 `Product` 表
2. 若找到 → 返回完整 SKU 信息
3. 若未找到 → 用 `sentence-transformers` 对 SKU ID 文本编码，在 `Product.embedding` 列做余弦相似度搜索，返回 top-3 最近邻
4. 将检索结果格式化为结构化上下文，传入 LLM Prompt

### 3.3 AI 定价生成

**是什么**：调用 Anthropic Claude API，以定价分析师角色，根据商品上下文输出建议价格。

**触发时机**：知识库检索完成后，Celery 任务自动调用，异步执行。

**输出内容**：
- `recommended_price`：建议零售价（美元，保留两位小数）
- `price_range.min`：最低可接受价格
- `price_range.max`：最高可接受价格
- `expected_margin`：预期毛利率（0~1 之间的小数）
- `reasoning`：定价依据说明（中文，2-3 句话）

### 3.4 进度查询与结果展示

**是什么**：前端每 2 秒轮询请求状态，处理完成后展示结果表格。

**状态流转**：
```
pending → processing → completed
                    ↘ failed
```

**结果表格列**：SKU ID | 建议价 | 最低价 | 最高价 | 预期利润率 | 定价依据

### 3.5 CSV 结果下载

**是什么**：将定价结果导出为 CSV 文件供下载。

**CSV 输出格式**：
```csv
sku_id,recommended_price,price_min,price_max,expected_margin,reasoning
SKU-001,29.99,25.00,35.00,0.35,"基于成本加成35%，同细类商品价格区间参考..."
SKU-002,49.99,45.00,55.00,0.28,"..."
```

---

## 4. 数据模型

### 4.1 Product（新增）
存储预导入的 SKU 商品信息，是知识库 Agent 的数据源。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID, PK | 主键 |
| `sku_id` | VARCHAR(50), UNIQUE | 商品 SKU 编号，索引字段 |
| `product_name` | VARCHAR(200) | 商品名称 |
| `large_class` | VARCHAR(100) | 大类（如：家电、食品、服装） |
| `fine_class` | VARCHAR(100) | 细类（如：冰箱、零食、女装上衣） |
| `cost_price` | DECIMAL(10,2) | 采购成本价（USD） |
| `inventory` | INTEGER | 当前库存数量 |
| `monthly_sales` | INTEGER | 近 30 天销量 |
| `embedding` | vector(384) | 句子嵌入向量（pgvector），all-MiniLM-L6-v2 |
| `created_at` | DateTimeField | 创建时间 |
| `updated_at` | DateTimeField | 更新时间 |

**对应旧模型**：无（全新）

---

### 4.2 PricingRequest（改自 Order）
一次批量定价请求，对应用户的一次 CSV 上传。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID, PK | 主键 |
| `request_id` | VARCHAR(20) | 人类可读的请求编号（如 PRC-2026-001） |
| `uploaded_filename` | VARCHAR(255) | 上传的文件名 |
| `sku_count` | INTEGER | 本次上传的 SKU 总数 |
| `status` | CharField | pending / processing / completed / failed |
| `error_message` | TextField | 失败时的错误信息 |
| `created_at` | DateTimeField | 请求创建时间 |
| `updated_at` | DateTimeField | 状态更新时间 |
| `completed_at` | DateTimeField | 完成时间（nullable） |

**对应旧模型**：`Order`（原有 `patient_id`, `provider_id`, `medication_name` 等字段全部移除）

---

### 4.3 PricingResult（改自 CarePlan）
每个 SKU 的定价结果，一个 PricingRequest 对应多条 PricingResult。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID, PK | 主键 |
| `request` | ForeignKey(PricingRequest) | 所属请求（原 OneToOne → ForeignKey） |
| `sku_id` | VARCHAR(50) | SKU 编号（冗余存储，方便查询） |
| `recommended_price` | DECIMAL(10,2) | LLM 建议零售价 |
| `price_min` | DECIMAL(10,2) | 最低可接受价格 |
| `price_max` | DECIMAL(10,2) | 最高可接受价格 |
| `expected_margin` | DECIMAL(5,4) | 预期毛利率（如 0.3500） |
| `reasoning` | TextField | 定价依据说明 |
| `llm_model` | VARCHAR(100) | 使用的 LLM 模型名称 |
| `generated_at` | DateTimeField | 生成时间 |

**对应旧模型**：`CarePlan`（原 `content` 纯文本字段拆分为多个结构化字段；原 OneToOne 关系改为 ForeignKey）

---

### 4.4 实体关系图

```
PricingRequest
    │  id, request_id, uploaded_filename,
    │  sku_count, status, error_message,
    │  created_at, updated_at, completed_at
    │
    └──< PricingResult (1:N)
            id, sku_id, recommended_price,
            price_min, price_max,
            expected_margin, reasoning,
            llm_model, generated_at

Product (独立)
    id, sku_id, product_name,
    large_class, fine_class,
    cost_price, inventory,
    monthly_sales, embedding
```

---

## 5. 知识库 Agent 设计

### 5.1 数据源

**商品数据库**：PostgreSQL `Product` 表，由运维人员预先使用管理命令 `load_sku_data` 导入。

**示例数据**（Demo 用，约 50 条）：
```
SKU-001 | 无线蓝牙耳机 | 电子产品 | 音频设备 | $12.50 | 230件 | 145件/月
SKU-002 | 有机燕麦片 | 食品 | 谷物早餐 | $3.20 | 500件 | 320件/月
SKU-003 | 女士运动上衣 | 服装 | 女装运动 | $8.90 | 180件 | 67件/月
...
```

### 5.2 向量嵌入策略

**模型**：`sentence-transformers/all-MiniLM-L6-v2`（本地加载，无需 API）
- 向量维度：384
- 编码文本：`f"{sku_id} {product_name} {large_class} {fine_class}"`
- pgvector 列定义：`embedding vector(384)`

**嵌入生成时机**：导入 SKU 数据时，管理命令 `load_sku_data` 自动调用模型生成并存储向量。

### 5.3 检索流程

```python
class KnowledgeBaseAgent:
    def retrieve(self, sku_id: str) -> dict:
        # 1. 精确匹配
        product = Product.objects.filter(sku_id=sku_id).first()
        if product:
            return self._format_context(product)

        # 2. 向量相似度搜索（fallback）
        query_embedding = self.model.encode(sku_id)
        similar_products = Product.objects.order_by(
            L2Distance('embedding', query_embedding)
        )[:3]
        return self._format_context_multi(similar_products)
```

### 5.4 上下文构建

检索到 SKU 信息后，格式化为结构化文本传入 LLM Prompt：

```
商品信息：
- SKU ID: {sku_id}
- 商品名: {product_name}
- 大类: {large_class} | 细类: {fine_class}
- 采购成本: ${cost_price}
- 当前库存: {inventory} 件
- 近30天销量: {monthly_sales} 件/月
```

---

## 6. LLM 定价 Prompt 设计规范

### 6.1 角色设定

```
你是一名专业的零售定价分析师，服务于一家综合零售商（类似 Walmart/Target）。
你的目标是在市场可接受的价格范围内，最大化商品的毛利率。
```

### 6.2 完整 Prompt 结构

```
[角色设定]
你是一名专业的零售定价分析师，服务于一家综合零售商（类似 Walmart/Target）。
你的目标是在市场可接受的价格范围内，最大化商品的毛利率。

[商品信息]
{sku_context}

[定价任务]
请基于以上商品信息，为该商品制定零售价格建议。
考虑因素：
1. 成本加成：确保足够的毛利率（目标 25%-50%）
2. 市场定位：考虑商品大类和细类的通常定价区间
3. 库存状态：库存高时可适当保守定价，库存低时可略微提高价格
4. 销售速度：销量好的商品价格弹性较小

[输出要求]
请严格以 JSON 格式输出，不要包含任何其他文字：
{
  "sku_id": "商品SKU编号",
  "recommended_price": 建议零售价（数字，保留两位小数）,
  "price_range": {
    "min": 最低可接受价格（数字）,
    "max": 最高可接受价格（数字）
  },
  "expected_margin": 预期毛利率（0到1之间的小数）,
  "reasoning": "定价依据说明（中文，2-3句话）"
}
```

### 6.3 JSON 解析与容错

- 使用 `json.loads()` 解析 LLM 输出
- 若解析失败，设置 PricingResult 状态为 `failed`，记录原始输出便于调试
- 使用 Celery 重试机制（max_retries=3，指数退避），避免临时 API 错误

---

## 7. 核心业务流程

### 主流程：批量 SKU 定价

```
步骤 1：分析师打开页面
  └─ 看到 CSV 上传区域

步骤 2：上传 CSV 文件
  └─ 前端 POST /api/pricing/upload/
  └─ 后端解析 CSV，提取 sku_id 列
  └─ 创建 PricingRequest（status: pending）
  └─ 返回 {request_id, sku_count}

步骤 3：触发异步任务
  └─ Celery 任务 generate_pricing(request_id) 入队
  └─ PricingRequest.status → processing

步骤 4：前端轮询状态
  └─ 每 2 秒 GET /api/pricing/{request_id}/
  └─ 显示进度（已完成 X / 总计 Y 个 SKU）

步骤 5：Celery 任务处理（对每个 SKU 循环）
  └─ KnowledgeBaseAgent.retrieve(sku_id)
      └─ 精确匹配 OR 向量相似度搜索
  └─ build_pricing_prompt(sku_context)
  └─ call_llm(prompt) → 调用 Claude API
  └─ 解析 JSON 响应
  └─ 创建 PricingResult 记录

步骤 6：所有 SKU 处理完成
  └─ PricingRequest.status → completed
  └─ 前端检测到 completed → 展示结果表格

步骤 7：查看与下载
  └─ 前端显示结果表格（SKU ID | 建议价 | 区间 | 利润率 | 依据）
  └─ 点击"下载 CSV"→ GET /api/pricing/{request_id}/download/
  └─ 下载 pricing_results_{request_id}.csv
```

### 错误处理流程

```
LLM 调用失败
  └─ Celery 自动重试（最多 3 次，指数退避：10s → 20s → 40s）
  └─ 3 次全部失败 → 该 SKU 的 PricingResult 标记 failed
  └─ PricingRequest.status 仍为 completed（部分成功）
  └─ 下载 CSV 中失败的 SKU 行显示 "ERROR"

SKU 在数据库中不存在
  └─ 向量搜索返回最相似的商品作为参考
  └─ Prompt 中注明"以下信息为最相近商品参考"
  └─ 结果正常生成，reasoning 中包含"SKU未找到，基于相似商品..."说明
```

---

## 8. API 接口规范

### POST /api/pricing/upload/
上传 CSV 文件，创建定价请求。

**请求**：`multipart/form-data`，字段名 `file`

**响应 201**：
```json
{
  "request_id": "PRC-2026-001",
  "sku_count": 10,
  "status": "pending"
}
```

**响应 400**：文件格式错误或缺少 `sku_id` 列

---

### GET /api/pricing/{request_id}/
查询定价请求进度和结果。

**响应 200**：
```json
{
  "request_id": "PRC-2026-001",
  "status": "completed",
  "sku_count": 10,
  "completed_count": 10,
  "results": [
    {
      "sku_id": "SKU-001",
      "recommended_price": 29.99,
      "price_range": {"min": 25.0, "max": 35.0},
      "expected_margin": 0.35,
      "reasoning": "基于成本 $12.50，加成 140% 设定建议价..."
    }
  ]
}
```

---

### GET /api/pricing/{request_id}/download/
下载定价结果 CSV。

**响应 200**：`Content-Type: text/csv`，文件名 `pricing_results_{request_id}.csv`

**对应旧接口**：`GET /api/orders/{uuid}/download`（返回 .txt 改为 .csv）

---

## 9. 非功能需求

| 类别 | 要求（Demo 级别） |
|------|-----------------|
| **性能** | 单次上传 50 个 SKU，5 分钟内完成（含 LLM 调用） |
| **可用性** | Docker Compose 本地启动，无高可用要求 |
| **安全** | 无认证（Demo），API Key 通过 .env 文件管理 |
| **数据安全** | 定价数据存储在本地 PostgreSQL，不传输到外部 |
| **审计日志** | PricingRequest + PricingResult 表记录完整请求历史 |
| **错误恢复** | Celery 重试机制（3次，指数退避）自动处理临时 LLM 故障 |

---

## 10. MVP 范围界定

### 第一版（当前目标）包含：
- [x] CSV 文件上传（批量 SKU ID）
- [x] 知识库 Agent（pgvector 向量检索 + sentence-transformers 本地嵌入）
- [x] LLM 定价分析（Claude API，定价分析师 Prompt）
- [x] 异步批量处理（Celery + Redis）
- [x] 进度轮询与结果展示
- [x] CSV 结果下载
- [x] 示例 SKU 数据导入（管理命令）

### 第一版不包含：
- [ ] 用户登录/认证
- [ ] 实时竞品价格抓取
- [ ] 定价规则引擎
- [ ] 历史定价记录的可视化分析
- [ ] ERP/WMS 系统集成

---

## 11. 迭代路线图

### Phase 2：数据增强
- 接入真实竞品价格 API（如 价格比价平台）
- 支持 ERP 系统数据同步（自动更新库存和成本）
- 增加季节性因子（节假日、促销期）

### Phase 3：规则引擎
- 可配置的定价规则（最低利润率保护、最高涨幅限制）
- 品类级别的定价策略模板
- 价格变动审批流程

### Phase 4：自动化与监控
- 定时批量定价任务（每日自动更新价格建议）
- 定价效果追踪（建议价 vs 实际成交价 vs 毛利率）
- 异常定价告警（价格偏离历史区间超过阈值）

### Phase 5：多用户协作
- 用户登录和权限管理（分析师/品类经理/管理层）
- 定价建议审批工作流
- 定价历史和版本对比
