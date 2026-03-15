"""
pricing/tasks.py — Celery 异步定价任务

generate_pricing(request_id, sku_ids)
    对一次 CSV 上传中的每个 SKU 异步执行：
      1. KnowledgeBaseAgent 检索商品上下文
      2. build_pricing_prompt() 构建 Prompt
      3. call_llm() 调用 Claude API
      4. 将结果写入 PricingResult 表

两级错误隔离策略：
  - 批次级灾难错误（DB 断连无法获取 PricingRequest）
      → 指数退避重试最多 3 次（10s → 20s → 40s）
      → 耗尽后将 PricingRequest.status 标记为 'failed'
  - 单 SKU 错误（LLM JSON 解析失败、SKU 不在知识库）
      → 创建带 error_message 的 PricingResult
      → continue 处理下一个 SKU，不中断整批任务
"""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=10,   # 初始重试延迟（秒）
    acks_late=True,           # 任务执行完才 ack，防止 worker 崩溃时任务丢失
    reject_on_worker_lost=True,
)
def generate_pricing(self, request_id: str, sku_ids: list):
    """
    异步批量定价任务。

    参数
    ----
    request_id : str
        PricingRequest 的 UUID 字符串
    sku_ids : list[str]
        本次上传的 SKU ID 列表（由 Step 5 上传视图在 dispatch 时传入）

    注意事项
    --------
    - 所有 Django ORM / services / agents 的导入放在函数体内，
      确保 Celery worker 启动时不触发 AppRegistryNotReady。
    - KnowledgeBaseAgent 在任务开始时实例化一次，
      复用 sentence-transformers 模型（加载耗时 ~2-4s，只发生一次）。
    - `save(update_fields=[...])` 避免意外覆盖其他字段，减少 SQL 锁竞争。
    """
    # ---- 延迟导入，Celery worker 安全 ----
    from django.utils import timezone
    from .models import PricingRequest, PricingResult
    from .agents import KnowledgeBaseAgent
    from .services import build_pricing_prompt, call_llm

    logger.info(
        "[generate_pricing] 任务开始: request_id=%s, sku_count=%d",
        request_id,
        len(sku_ids),
    )

    # ================================================================
    # 步骤 1：获取 PricingRequest，标记为 processing
    # 若此处失败（DB 断连等）属于灾难性错误，走重试路径
    # ================================================================
    try:
        pricing_request = PricingRequest.objects.get(id=request_id)
        pricing_request.status = 'processing'
        pricing_request.save(update_fields=['status', 'updated_at'])
        logger.info("[generate_pricing] PricingRequest 状态 → processing")
    except Exception as exc:
        logger.exception(
            "[generate_pricing] 获取/更新 PricingRequest 失败（灾难性错误）: %s", exc
        )
        # 显式指数退避：10s → 20s → 40s
        countdown = 10 * (2 ** self.request.retries)
        try:
            raise self.retry(exc=exc, countdown=countdown)
        except self.MaxRetriesExceededError:
            # 重试耗尽：best-effort 将状态写为 failed
            try:
                PricingRequest.objects.filter(id=request_id).update(
                    status='failed',
                    error_message=f"任务重试耗尽。最后错误：{exc}",
                )
                logger.error(
                    "[generate_pricing] 最大重试次数耗尽，request_id=%s 已标记为 failed",
                    request_id,
                )
            except Exception:
                # DB 已不可用，无法写入，只能放弃
                logger.error(
                    "[generate_pricing] 无法写入 failed 状态（DB 不可用），request_id=%s",
                    request_id,
                )
            raise

    # ================================================================
    # 步骤 2：实例化 KnowledgeBaseAgent（一次，复用于所有 SKU）
    # ================================================================
    agent = KnowledgeBaseAgent()
    logger.info("[generate_pricing] KnowledgeBaseAgent 已实例化")

    # ================================================================
    # 步骤 3：逐 SKU 处理（单 SKU 失败不影响其他 SKU）
    # ================================================================
    for sku_id in sku_ids:
        logger.info("[generate_pricing] 开始处理 SKU: %s", sku_id)

        try:
            # 3a. 知识库检索：精确匹配优先，失败则向量 fallback
            context = agent.retrieve(sku_id=sku_id, query_text=sku_id)

            # 3b. 精确 + 向量均无结果
            if context is None:
                logger.warning(
                    "[generate_pricing] SKU 不在知识库中: %s，写入 error_message", sku_id
                )
                PricingResult.objects.create(
                    request=pricing_request,
                    sku_id=sku_id,
                    error_message="SKU not found in knowledge base",
                )
                continue  # 不中断整批，继续下一个 SKU

            # 3c. 构建 Prompt
            prompt = build_pricing_prompt(context)
            logger.debug(
                "[generate_pricing] Prompt 构建完成: sku=%s, match_type=%s",
                sku_id,
                context.get('match_type'),
            )

            # 3d. 调用 Claude API
            result_dict = call_llm(prompt)
            logger.info(
                "[generate_pricing] LLM 返回成功: sku=%s, price=%.2f, model=%s",
                sku_id,
                result_dict.get('recommended_price', 0),
                result_dict.get('llm_model', ''),
            )

            # 3e. 写入 PricingResult（所有字段）
            PricingResult.objects.create(
                request=pricing_request,
                sku_id=sku_id,
                recommended_price=result_dict['recommended_price'],
                price_min=result_dict['price_range']['min'],
                price_max=result_dict['price_range']['max'],
                expected_margin=result_dict['expected_margin'],
                reasoning=result_dict.get('reasoning', ''),
                llm_model=result_dict.get('llm_model', ''),
            )
            logger.info("[generate_pricing] PricingResult 已写入: sku=%s", sku_id)

        except Exception as exc:
            # 单 SKU 失败：隔离错误，继续处理其余 SKU
            # 不触发 Celery 重试（避免因单 SKU 失败而重跑整批）
            logger.exception(
                "[generate_pricing] SKU 处理失败（已隔离）: sku=%s, error=%s",
                sku_id,
                exc,
            )
            PricingResult.objects.create(
                request=pricing_request,
                sku_id=sku_id,
                error_message=str(exc),
            )

    # ================================================================
    # 步骤 4：所有 SKU 处理完毕，更新请求状态为 completed
    # ================================================================
    pricing_request.status = 'completed'
    pricing_request.completed_at = timezone.now()
    pricing_request.save(update_fields=['status', 'completed_at', 'updated_at'])

    completed_count = pricing_request.results.count()
    logger.info(
        "[generate_pricing] 任务完成: request_id=%s, results_written=%d",
        request_id,
        completed_count,
    )
