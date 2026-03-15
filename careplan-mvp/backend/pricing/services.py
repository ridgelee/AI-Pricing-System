"""
pricing/services.py — 业务逻辑层

build_pricing_prompt()  : 将 SKU 上下文 dict 渲染为 Claude 定价分析师 Prompt。
call_llm()              : 调用 Anthropic API，解析 JSON，返回定价结果 dict。
"""
import json
import logging
import os
import re

logger = logging.getLogger(__name__)


def build_pricing_prompt(sku_context: dict) -> str:
    """
    将 KnowledgeBaseAgent.retrieve() 返回的 SKU 上下文 dict 渲染为
    完整的 Claude 定价分析师 Prompt（完全按 PRD 第 6.2 节规范）。

    参数
    ----
    sku_context : dict
        KnowledgeBaseAgent.retrieve() 的返回值，包含：
          match_type       : 'exact' 或 'vector'
          sku_id           : 知识库中匹配到的 Product SKU ID
          original_sku_id  : 仅 match_type='vector' 时存在，用户原始 SKU ID
          product_name, large_class, fine_class, cost_price,
          inventory, monthly_sales

    返回
    ----
    str : 完整 Prompt 字符串，直接传给 Claude messages API
    """
    match_type = sku_context.get('match_type', 'exact')

    # ---- 商品信息区块 ----
    product_block = (
        "[商品信息]\n"
        f"- SKU ID: {sku_context['sku_id']}\n"
        f"- 商品名: {sku_context['product_name']}\n"
        f"- 大类: {sku_context['large_class']} | 细类: {sku_context['fine_class']}\n"
        f"- 采购成本: ${sku_context['cost_price']}\n"
        f"- 当前库存: {sku_context['inventory']} 件\n"
        f"- 近30天销量: {sku_context['monthly_sales']} 件/月"
    )

    # ---- 向量 fallback 时在商品信息之后追加说明 ----
    vector_note = ""
    if match_type == 'vector':
        original_sku_id = sku_context.get('original_sku_id', '')
        vector_note = (
            f'\n注意：SKU "{original_sku_id}" 在知识库中未找到，'
            '以下为最相近商品信息，请参考定价。'
        )

    prompt = (
        "你是一名专业的零售定价分析师，服务于一家综合零售商（类似 Walmart/Target）。\n"
        "你的目标是在市场可接受的价格范围内，最大化商品的毛利率。\n"
        "\n"
        f"{product_block}"
        f"{vector_note}"
        "\n"
        "\n"
        "[定价任务]\n"
        "请基于以上商品信息，为该商品制定零售价格建议。\n"
        "考虑因素：\n"
        "1. 成本加成：确保足够的毛利率（目标 25%-50%）\n"
        "2. 市场定位：考虑商品大类和细类的通常定价区间\n"
        "3. 库存状态：库存高时可适当保守定价，库存低时可略微提高价格\n"
        "4. 销售速度：销量好的商品价格弹性较小\n"
        "\n"
        "[输出要求]\n"
        "请严格以 JSON 格式输出，不要包含任何其他文字：\n"
        "{\n"
        f'  "sku_id": "{sku_context["sku_id"]}",\n'
        '  "recommended_price": 建议零售价（数字，保留两位小数）,\n'
        '  "price_range": {\n'
        '    "min": 最低可接受价格（数字）,\n'
        '    "max": 最高可接受价格（数字）\n'
        '  },\n'
        '  "expected_margin": 预期毛利率（0到1之间的小数）,\n'
        '  "reasoning": "定价依据说明（中文，2-3句话）"\n'
        "}"
    )
    return prompt


def call_llm(prompt: str) -> dict:
    """
    调用 Anthropic Claude API，解析 JSON 响应，返回定价结果 dict。

    返回
    ----
    dict 包含：
        recommended_price : float
        price_range       : {"min": float, "max": float}
        expected_margin   : float
        reasoning         : str
        llm_model         : str  (message.model，实际使用的模型名)

    异常
    ----
    ValueError           : JSON 解析失败，错误信息含原始响应便于调试
    anthropic.APIError   : Anthropic SDK API 错误，直接向上抛出
    """
    import anthropic
    from django.conf import settings

    api_key = settings.ANTHROPIC_API_KEY
    model_name = os.getenv('ANTHROPIC_MODEL', 'claude-sonnet-4-5')

    # Client 在函数体内创建：
    #   1. 避免模块级导入时 settings 未就绪（Celery worker 安全）
    #   2. 相对 LLM 网络往返（通常 1-5s），创建 client 的开销可忽略
    client = anthropic.Anthropic(api_key=api_key)

    logger.info(
        "[call_llm] 调用 Claude API: model=%s, prompt_len=%d",
        model_name, len(prompt)
    )

    message = client.messages.create(
        model=model_name,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    raw_text = message.content[0].text
    actual_model = message.model

    logger.debug(
        "[call_llm] 收到响应: model=%s, response_len=%d, raw_text_prefix=%r",
        actual_model, len(raw_text), raw_text[:100]
    )

    # ---- 去除 LLM 有时包裹的 markdown 代码围栏 ----
    # 处理 ```json ... ``` 和 ``` ... ``` 两种形式
    cleaned = re.sub(r'^```(?:json)?\s*', '', raw_text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*```$', '', cleaned.strip())

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"LLM 返回内容无法解析为 JSON。"
            f"解析错误: {exc}. "
            f"原始响应（前500字符）: {raw_text[:500]!r}"
        ) from exc

    # 将实际使用的模型名注入结果，供 PricingResult.llm_model 存储
    result['llm_model'] = actual_model

    logger.info(
        "[call_llm] 解析成功: recommended_price=%s, model=%s",
        result.get('recommended_price'), actual_model
    )
    return result
