"""
pricing/views.py — AI 定价系统 API 视图

PricingUploadView   POST  /api/pricing/upload/
    接收 multipart/form-data CSV 文件 → 解析 SKU ID 列表
    → 创建 PricingRequest → 触发 Celery 任务 → 返回 202

PricingDetailView   GET   /api/pricing/<request_id>/
    返回 PricingRequest 状态 + 所有 PricingResult（含成功/失败行）

PricingDownloadView GET   /api/pricing/<request_id>/download/
    生成并返回定价结果 CSV 文件（Content-Disposition: attachment）

错误处理：
  - BaseAppException（含 ValidationError）→ ExceptionHandlerMixin 捕获，返回 JSON
  - 未知异常 → 500 JSON
"""
import csv
import io
import logging

from django.http import JsonResponse, HttpResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from .exceptions import BaseAppException, ValidationError
from .serializers import serialize_pricing_request, serialize_pricing_detail

logger = logging.getLogger(__name__)


# ===========================================================================
# 异常处理 Mixin
# ===========================================================================

class ExceptionHandlerMixin:
    """
    统一异常处理，复用自 careplan-mvp。

    BaseAppException（业务异常）→ JSON：{'error': msg, 'code': code, 'type': type}
    未知异常                     → 500：{'error': 'Internal server error', 'detail': ...}
    """
    def dispatch(self, request, *args, **kwargs):
        try:
            return super().dispatch(request, *args, **kwargs)
        except BaseAppException as e:
            return JsonResponse(
                {'error': e.message, 'code': e.code, 'type': e.type},
                status=e.http_status,
            )
        except Exception as e:
            logger.exception("Unhandled exception in view: %s", e)
            return JsonResponse(
                {'error': 'Internal server error', 'detail': str(e)},
                status=500,
            )


# ===========================================================================
# 私有辅助函数
# ===========================================================================

def _parse_csv_sku_ids(file_obj) -> list:
    """
    从上传的文件对象中解析 SKU ID 列表。

    列名识别（大小写不敏感）：
      - 优先使用列名中包含 'sku' 的第一列
      - 找不到时 fallback 到第一列，并记录 WARNING

    编码处理：
      - 优先 utf-8-sig（自动剥离 Excel BOM）
      - 失败时回退 latin-1（兼容 Excel 导出的非 UTF-8 CSV）

    结果：去重（保留首次出现顺序）、去空白、过滤空值。

    抛出 ValidationError（400）当：
      - 文件无法读取
      - CSV 没有表头行
      - 找不到任何有效 SKU ID
    """
    # ---- 读取原始字节并解码 ----
    try:
        raw_bytes = file_obj.read()
    except Exception as exc:
        raise ValidationError(f"无法读取上传文件：{exc}")

    try:
        content = raw_bytes.decode('utf-8-sig')   # utf-8-sig 自动去 BOM
    except UnicodeDecodeError:
        content = raw_bytes.decode('latin-1')

    # ---- CSV 解析 ----
    reader = csv.DictReader(io.StringIO(content))
    headers = reader.fieldnames

    if not headers:
        raise ValidationError("CSV 文件为空或缺少表头行，请检查文件格式")

    # ---- 定位 SKU 列 ----
    sku_col = None
    for h in headers:
        if h and 'sku' in h.lower():
            sku_col = h
            break

    if sku_col is None:
        sku_col = headers[0]
        logger.warning(
            "[PricingUploadView] 未找到含 'sku' 的列名，使用第一列 '%s'", sku_col
        )
    else:
        logger.info("[PricingUploadView] 使用 SKU 列: '%s'", sku_col)

    # ---- 提取去重 SKU ID ----
    seen = set()
    sku_ids = []
    for row in reader:
        val = (row.get(sku_col) or '').strip()
        if val and val not in seen:
            seen.add(val)
            sku_ids.append(val)

    return sku_ids


# ===========================================================================
# 视图
# ===========================================================================

@method_decorator(csrf_exempt, name='dispatch')
class PricingUploadView(ExceptionHandlerMixin, View):
    """
    POST /api/pricing/upload/

    请求格式：multipart/form-data，字段名 'file'，文件类型 .csv
    成功响应：202 + PricingRequest 基本信息（含 request_id 供前端轮询）
    失败响应：400 ValidationError（无文件 / CSV 格式错误 / 无 SKU）

    流程：
      1. 提取上传文件
      2. 解析 CSV → SKU ID 列表（_parse_csv_sku_ids）
      3. 创建 PricingRequest（status='pending'）
      4. generate_pricing.delay(request_id, sku_ids) 触发异步任务
      5. 返回 202 + 序列化的 PricingRequest
    """

    def post(self, request):
        # 延迟导入：Celery worker 安全 + 避免循环导入
        from .models import PricingRequest
        from .tasks import generate_pricing

        # ---- 1. 取文件 ----
        uploaded_file = request.FILES.get('file')
        if uploaded_file is None:
            raise ValidationError(
                "请求中未找到 'file' 字段，请以 multipart/form-data 格式上传 CSV 文件"
            )

        original_filename = uploaded_file.name or 'upload.csv'
        logger.info("[PricingUploadView] 收到上传文件: %s, size=%d", original_filename, uploaded_file.size)

        # ---- 2. 解析 SKU ID 列表 ----
        sku_ids = _parse_csv_sku_ids(uploaded_file)
        if not sku_ids:
            raise ValidationError(
                "CSV 中未找到任何有效 SKU ID。"
                "请确保 CSV 有包含 'sku' 关键字的列标题，且列中有非空值。"
            )

        logger.info("[PricingUploadView] 解析到 SKU IDs: %d 个, 前5: %s", len(sku_ids), sku_ids[:5])

        # ---- 3. 创建 PricingRequest ----
        pricing_request = PricingRequest.objects.create(
            uploaded_filename=original_filename,
            sku_count=len(sku_ids),
            status='pending',
        )
        logger.info(
            "[PricingUploadView] PricingRequest 已创建: id=%s, sku_count=%d",
            pricing_request.id,
            len(sku_ids),
        )

        # ---- 4. 触发 Celery 异步任务 ----
        generate_pricing.delay(str(pricing_request.id), sku_ids)
        logger.info("[PricingUploadView] Celery 任务已触发: request_id=%s", pricing_request.id)

        # ---- 5. 返回 202 Accepted ----
        return JsonResponse(serialize_pricing_request(pricing_request), status=202)


class PricingDetailView(ExceptionHandlerMixin, View):
    """
    GET /api/pricing/<request_id>/

    返回 PricingRequest 的当前状态 + 所有 PricingResult。
    前端每 2 秒轮询此接口，直到 status 变为 'completed' 或 'failed'。

    成功响应：200 + 完整详情（含 results 数组）
    失败响应：404（request_id 不存在）
    """

    def get(self, request, request_id):
        from .models import PricingRequest

        try:
            pricing_request = PricingRequest.objects.get(id=request_id)
        except PricingRequest.DoesNotExist:
            return JsonResponse(
                {'error': f'PricingRequest {request_id} 不存在'},
                status=404,
            )

        return JsonResponse(serialize_pricing_detail(pricing_request), status=200)


class PricingDownloadView(ExceptionHandlerMixin, View):
    """
    GET /api/pricing/<request_id>/download/

    生成定价结果 CSV 文件并以附件形式返回。

    CSV 列（8 列）：
      SKU_ID | 建议价(USD) | 最低价(USD) | 最高价(USD) | 预期毛利率 | 定价依据 | 状态 | 错误信息

    成功行（status=success）：填写所有价格字段，错误信息留空。
    失败行（status=error）  ：价格字段留空，错误信息填写原因。

    编码：UTF-8 with BOM（\ufeff），确保 Excel 正确显示中文。

    前置条件：
      - 404：request_id 不存在
      - 409：任务尚未完成（pending / processing）
    """

    CSV_HEADERS = [
        'SKU_ID',
        '建议价(USD)',
        '最低价(USD)',
        '最高价(USD)',
        '预期毛利率',
        '定价依据',
        '状态',
        '错误信息',
    ]

    def get(self, request, request_id):
        from .models import PricingRequest

        # ---- 1. 获取请求 ----
        try:
            pricing_request = PricingRequest.objects.get(id=request_id)
        except PricingRequest.DoesNotExist:
            return JsonResponse(
                {'error': f'PricingRequest {request_id} 不存在'},
                status=404,
            )

        # ---- 2. 校验状态 ----
        if pricing_request.status in ('pending', 'processing'):
            return JsonResponse(
                {
                    'error': (
                        f'定价任务尚未完成（当前状态：{pricing_request.status}），请稍后再试'
                    )
                },
                status=409,
            )

        # ---- 3. 生成 CSV 内容 ----
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=self.CSV_HEADERS)
        writer.writeheader()

        for result in pricing_request.results.all():
            if result.error_message:
                # 定价失败行
                writer.writerow({
                    'SKU_ID': result.sku_id,
                    '建议价(USD)': '',
                    '最低价(USD)': '',
                    '最高价(USD)': '',
                    '预期毛利率': '',
                    '定价依据': '',
                    '状态': 'error',
                    '错误信息': result.error_message,
                })
            else:
                # 定价成功行
                margin_pct = (
                    f"{float(result.expected_margin) * 100:.2f}%"
                    if result.expected_margin is not None else ''
                )
                writer.writerow({
                    'SKU_ID': result.sku_id,
                    '建议价(USD)': (
                        f"{float(result.recommended_price):.2f}"
                        if result.recommended_price is not None else ''
                    ),
                    '最低价(USD)': (
                        f"{float(result.price_min):.2f}"
                        if result.price_min is not None else ''
                    ),
                    '最高价(USD)': (
                        f"{float(result.price_max):.2f}"
                        if result.price_max is not None else ''
                    ),
                    '预期毛利率': margin_pct,
                    '定价依据': result.reasoning,
                    '状态': 'success',
                    '错误信息': '',
                })

        # BOM + CSV 内容（Excel 打开中文不乱码）
        csv_content = '\ufeff' + output.getvalue()
        output.close()

        # ---- 4. 构造下载响应 ----
        short_id = str(pricing_request.id)[:8]
        safe_filename = f"pricing_results_{short_id}.csv"

        response = HttpResponse(csv_content, content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{safe_filename}"'

        logger.info(
            "[PricingDownloadView] CSV 下载: request_id=%s, rows=%d",
            pricing_request.id,
            pricing_request.results.count(),
        )
        return response
