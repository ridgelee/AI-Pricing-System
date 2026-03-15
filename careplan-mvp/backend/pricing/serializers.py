"""
pricing/serializers.py — 序列化工具函数

serialize_pricing_result(result)      : PricingResult ORM → dict
serialize_pricing_request(req)        : PricingRequest ORM → 基本信息 dict（不含 results）
serialize_pricing_detail(req)         : PricingRequest + 所有 PricingResult → 完整详情 dict
"""
import logging

logger = logging.getLogger(__name__)


def serialize_pricing_result(result) -> dict:
    """
    将单个 PricingResult ORM 实例序列化为 dict。

    Decimal 字段转为 float（JSON 可序列化），None 保留为 null。
    """
    return {
        'result_id': str(result.id),
        'sku_id': result.sku_id,
        'recommended_price': float(result.recommended_price) if result.recommended_price is not None else None,
        'price_min': float(result.price_min) if result.price_min is not None else None,
        'price_max': float(result.price_max) if result.price_max is not None else None,
        'expected_margin': float(result.expected_margin) if result.expected_margin is not None else None,
        'reasoning': result.reasoning,
        'llm_model': result.llm_model,
        'error_message': result.error_message,
        'generated_at': result.generated_at.isoformat(),
    }


def serialize_pricing_request(pricing_request) -> dict:
    """
    将 PricingRequest ORM 实例序列化为基本信息 dict（不含 results 列表）。
    用于上传接口的 202 响应，避免在任务开始前就查询空的 results 集合。
    """
    return {
        'request_id': str(pricing_request.id),
        'status': pricing_request.status,
        'sku_count': pricing_request.sku_count,
        'uploaded_filename': pricing_request.uploaded_filename,
        'error_message': pricing_request.error_message,
        'created_at': pricing_request.created_at.isoformat(),
        'completed_at': (
            pricing_request.completed_at.isoformat()
            if pricing_request.completed_at else None
        ),
    }


def serialize_pricing_detail(pricing_request) -> dict:
    """
    将 PricingRequest + 所有关联的 PricingResult 序列化为完整详情 dict。
    用于进度查询接口的 200 响应。
    results 按 generated_at 升序排列（模型 Meta 已定义）。
    """
    results = pricing_request.results.all()
    return {
        'request_id': str(pricing_request.id),
        'status': pricing_request.status,
        'sku_count': pricing_request.sku_count,
        'completed_count': pricing_request.completed_count,
        'uploaded_filename': pricing_request.uploaded_filename,
        'error_message': pricing_request.error_message,
        'created_at': pricing_request.created_at.isoformat(),
        'completed_at': (
            pricing_request.completed_at.isoformat()
            if pricing_request.completed_at else None
        ),
        'results': [serialize_pricing_result(r) for r in results],
    }
