import uuid
from django.db import models
from pgvector.django import VectorField


class Product(models.Model):
    """
    商品知识库（SKU 数据）。
    由管理命令 load_sku_data 预先导入，embedding 列由 sentence-transformers 生成。
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sku_id = models.CharField(max_length=50, unique=True, db_index=True)
    product_name = models.CharField(max_length=200)
    large_class = models.CharField(max_length=100)   # 大类，如：电子产品、食品、服装
    fine_class = models.CharField(max_length=100)    # 细类，如：音频设备、零食、女装上衣
    cost_price = models.DecimalField(max_digits=10, decimal_places=2)  # 采购成本（USD）
    inventory = models.IntegerField(default=0)        # 当前库存数量
    monthly_sales = models.IntegerField(default=0)   # 近 30 天销量

    # pgvector 向量列（all-MiniLM-L6-v2 输出 384 维）
    embedding = VectorField(dimensions=384, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'pricing_product'

    def __str__(self):
        return f"{self.sku_id} - {self.product_name}"


class PricingRequest(models.Model):
    """
    一次批量定价请求，对应用户的一次 CSV 上传。
    一个 PricingRequest 对应多条 PricingResult（一对多）。
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    uploaded_filename = models.CharField(max_length=255, default='upload.csv')
    sku_count = models.IntegerField(default=0)        # 本次上传的 SKU 总数
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'pricing_request'
        ordering = ['-created_at']

    def __str__(self):
        return f"PricingRequest({self.id}, status={self.status}, skus={self.sku_count})"

    @property
    def completed_count(self):
        """已完成处理的 SKU 数量"""
        return self.results.count()


class PricingResult(models.Model):
    """
    单个 SKU 的定价结果。
    ForeignKey 到 PricingRequest（一对多，替代原 CarePlan 的 OneToOne）。
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(
        PricingRequest,
        on_delete=models.CASCADE,
        related_name='results'
    )

    sku_id = models.CharField(max_length=50)          # 冗余存储，方便查询
    recommended_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    price_min = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    price_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    expected_margin = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)  # 如 0.3500
    reasoning = models.TextField(blank=True, default='')

    # LLM 元数据
    llm_model = models.CharField(max_length=100, blank=True, default='')
    error_message = models.TextField(blank=True, default='')  # 单个 SKU 失败时的错误信息

    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'pricing_result'
        ordering = ['generated_at']

    def __str__(self):
        return f"PricingResult(sku={self.sku_id}, price={self.recommended_price})"
