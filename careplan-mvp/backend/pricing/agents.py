"""
pricing/agents.py — Knowledge Base Agent

从 PostgreSQL + pgvector 知识库中检索 SKU 商品上下文。

检索策略：
  1. 精确匹配（优先）：直接按 sku_id 查询 Product 表
  2. 向量相似度（fallback）：用 sentence-transformers 编码 query_text，
     CosineDistance 搜索，返回最相近商品（top-3，取第 1 条）

SentenceTransformer 模型采用懒加载单例，避免：
  - Django 启动时 AppRegistryNotReady
  - Celery worker boot 时重复加载
"""

import logging
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 懒加载单例：首次调用 _get_model() 时初始化，此后复用
# CPython GIL 保证 _model = SentenceTransformer(...) 赋值是原子的，线程安全
# ---------------------------------------------------------------------------
_model = None


def _get_model():
    """
    返回缓存的 SentenceTransformer 实例，首次调用时加载模型。

    模型加载耗时约 2-4 秒（PyTorch + HuggingFace weights），
    懒加载确保只在真正需要 embedding 时才触发，不影响 Django 启动速度。
    """
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        model_name = getattr(settings, 'SENTENCE_TRANSFORMERS_MODEL', 'all-MiniLM-L6-v2')
        logger.info("[KnowledgeBaseAgent] 加载 SentenceTransformer 模型: %s", model_name)
        _model = SentenceTransformer(model_name)
        logger.info("[KnowledgeBaseAgent] 模型加载完成")
    return _model


class KnowledgeBaseAgent:
    """
    SKU 知识库检索 Agent（无状态，可重复实例化）。

    由于 _model 是模块级单例，多个实例共享同一个已加载的模型，不会重复加载。

    典型用法（Step 4 tasks.py 中）：
        agent = KnowledgeBaseAgent()
        context = agent.retrieve(sku_id='ELE-001', query_text='ELE-001')
        # context 是 dict 或 None
    """

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def retrieve(self, sku_id: str, query_text: str = None) -> Optional[dict]:
        """
        检索 SKU 商品上下文。

        参数
        ----
        sku_id : str
            用户 CSV 中上传的 SKU ID（精确匹配优先）
        query_text : str, optional
            若精确匹配失败，用此文本做向量检索 fallback。
            通常传入 sku_id 本身，让向量模型寻找最近邻商品。
            若为 None 且 sku_id 不存在，直接返回 None。

        返回
        ----
        dict 或 None
            包含所有商品字段的平铺 dict，附加 `match_type` 字段：
              - 'exact'  : 精确匹配到 sku_id
              - 'vector' : 向量相似度 fallback 匹配，
                           另附 `original_sku_id` 字段保留原始查询 ID
            若完全找不到，返回 None。
        """
        # ---- 策略 1：精确匹配 ----
        product = self._exact_match(sku_id)
        if product is not None:
            logger.info("[KnowledgeBaseAgent] 精确匹配成功 sku_id=%s", sku_id)
            result = self._to_dict(product)
            result['match_type'] = 'exact'
            return result

        # ---- 策略 2：向量相似度 fallback ----
        if query_text is None:
            logger.warning(
                "[KnowledgeBaseAgent] sku_id=%s 未找到，且未提供 query_text，返回 None",
                sku_id,
            )
            return None

        logger.info(
            "[KnowledgeBaseAgent] sku_id=%s 精确匹配失败，向量检索 fallback，query_text=%r",
            sku_id,
            query_text,
        )
        candidates = self._vector_search(query_text, top_k=3)
        if not candidates:
            logger.warning(
                "[KnowledgeBaseAgent] 向量检索无结果，sku_id=%s", sku_id
            )
            return None

        best = candidates[0]
        result = self._to_dict(best)
        result['match_type'] = 'vector'
        result['original_sku_id'] = sku_id  # 保留原始未匹配的 SKU ID
        logger.info(
            "[KnowledgeBaseAgent] 向量匹配: original_sku=%s → matched_sku=%s (distance=%.4f)",
            sku_id,
            best.sku_id,
            getattr(best, 'distance', -1.0),
        )
        return result

    # ------------------------------------------------------------------
    # 私有方法
    # ------------------------------------------------------------------

    def _exact_match(self, sku_id: str):
        """
        按 sku_id 精确查询 Product 表。

        sku_id 字段有 UNIQUE + db_index，此查询极快（O(log n)）。
        ORM 导入在方法体内，防止 AppRegistryNotReady。
        """
        from .models import Product
        return Product.objects.filter(sku_id=sku_id).first()

    def _vector_search(self, query_text: str, top_k: int = 3):
        """
        将 query_text 编码为向量，按余弦距离（CosineDistance）检索最近邻。

        CosineDistance 取值范围 [0, 2]，值越小越相似。
        order_by('distance') 升序 → 最相近的排前面。
        """
        from .models import Product
        from pgvector.django import CosineDistance

        query_vector = self._embed(query_text)
        qs = (
            Product.objects
            .annotate(distance=CosineDistance('embedding', query_vector))
            .order_by('distance')[:top_k]
        )
        return list(qs)

    def _embed(self, text: str) -> list:
        """
        用 sentence-transformers 将文本编码为 384 维浮点向量（Python list）。

        .tolist() 将 numpy.ndarray(float32) 转为 list[float]，
        确保 psycopg2 / pgvector adapter 能正确序列化。
        """
        model = _get_model()
        vector = model.encode(text)
        return vector.tolist()

    @staticmethod
    def _to_dict(product) -> dict:
        """
        将 Product ORM 实例序列化为平铺 dict。

        包含所有 LLM Prompt 所需字段，不含 embedding 向量（大且 LLM 不需要）。
        """
        return {
            'id': str(product.id),
            'sku_id': product.sku_id,
            'product_name': product.product_name,
            'large_class': product.large_class,
            'fine_class': product.fine_class,
            'cost_price': float(product.cost_price),
            'inventory': product.inventory,
            'monthly_sales': product.monthly_sales,
        }
