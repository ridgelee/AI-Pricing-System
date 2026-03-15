"""
management/commands/load_sku_data.py

Django 管理命令：将约 50 条示例 SKU 数据（含向量嵌入）导入 Product 表。

用法：
    python manage.py load_sku_data            # 导入全部 50 条（幂等）
    python manage.py load_sku_data --clear    # 先清空再导入

幂等性：使用 update_or_create(sku_id=...) 实现，可安全多次执行。
Embedding 文本格式：f"{sku_id} {product_name} {large_class} {fine_class}"
（与 KnowledgeBaseAgent._vector_search 的 fallback 查询文本保持一致）
"""

import logging
from django.core.management.base import BaseCommand
from django.conf import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 示例 SKU 数据 — 50 条，覆盖 5 大类，模拟综合零售商（Walmart/Target 类型）
#
# 字段说明：
#   sku_id        : 系统 SKU 编号（唯一键）
#   product_name  : 商品全名
#   large_class   : 大类（5 类）
#   fine_class    : 细类
#   cost_price    : 采购成本（USD 字符串，避免浮点精度问题）
#   inventory     : 当前库存数量
#   monthly_sales : 过去 30 天销售数量
# ---------------------------------------------------------------------------

SAMPLE_SKUS = [
    # ---- Electronics（电子产品，10 条，ELE-001 ~ ELE-010）----
    {
        'sku_id': 'ELE-001',
        'product_name': 'Wireless Bluetooth Earbuds with Charging Case',
        'large_class': 'Electronics',
        'fine_class': 'Audio Devices',
        'cost_price': '12.50',
        'inventory': 850,
        'monthly_sales': 420,
    },
    {
        'sku_id': 'ELE-002',
        'product_name': '65-Inch 4K Smart TV LED Display',
        'large_class': 'Electronics',
        'fine_class': 'Televisions',
        'cost_price': '380.00',
        'inventory': 95,
        'monthly_sales': 38,
    },
    {
        'sku_id': 'ELE-003',
        'product_name': 'USB-C Fast Charging Power Bank 20000mAh',
        'large_class': 'Electronics',
        'fine_class': 'Mobile Accessories',
        'cost_price': '18.75',
        'inventory': 620,
        'monthly_sales': 310,
    },
    {
        'sku_id': 'ELE-004',
        'product_name': 'Mechanical Gaming Keyboard RGB Backlit',
        'large_class': 'Electronics',
        'fine_class': 'Computer Peripherals',
        'cost_price': '35.00',
        'inventory': 240,
        'monthly_sales': 95,
    },
    {
        'sku_id': 'ELE-005',
        'product_name': 'Portable Bluetooth Speaker Waterproof IPX7',
        'large_class': 'Electronics',
        'fine_class': 'Audio Devices',
        'cost_price': '22.00',
        'inventory': 430,
        'monthly_sales': 185,
    },
    {
        'sku_id': 'ELE-006',
        'product_name': '10-inch Android Tablet 64GB Wi-Fi',
        'large_class': 'Electronics',
        'fine_class': 'Tablets',
        'cost_price': '95.00',
        'inventory': 175,
        'monthly_sales': 62,
    },
    {
        'sku_id': 'ELE-007',
        'product_name': 'Smart Home Security Camera 1080P Night Vision',
        'large_class': 'Electronics',
        'fine_class': 'Smart Home',
        'cost_price': '28.50',
        'inventory': 510,
        'monthly_sales': 230,
    },
    {
        'sku_id': 'ELE-008',
        'product_name': 'Noise Cancelling Over-Ear Headphones',
        'large_class': 'Electronics',
        'fine_class': 'Audio Devices',
        'cost_price': '55.00',
        'inventory': 310,
        'monthly_sales': 140,
    },
    {
        'sku_id': 'ELE-009',
        'product_name': 'Wireless Charging Pad 15W Qi Compatible',
        'large_class': 'Electronics',
        'fine_class': 'Mobile Accessories',
        'cost_price': '8.90',
        'inventory': 980,
        'monthly_sales': 560,
    },
    {
        'sku_id': 'ELE-010',
        'product_name': 'Smart LED Light Strip 16 Million Colors WiFi',
        'large_class': 'Electronics',
        'fine_class': 'Smart Home',
        'cost_price': '11.20',
        'inventory': 760,
        'monthly_sales': 390,
    },

    # ---- Food & Beverages（食品饮料，10 条，FOD-001 ~ FOD-010）----
    {
        'sku_id': 'FOD-001',
        'product_name': 'Organic Rolled Oats Old Fashioned 42oz',
        'large_class': 'Food & Beverages',
        'fine_class': 'Breakfast Cereals',
        'cost_price': '3.20',
        'inventory': 2400,
        'monthly_sales': 1250,
    },
    {
        'sku_id': 'FOD-002',
        'product_name': 'Cold Brew Coffee Concentrate 32oz Bottle',
        'large_class': 'Food & Beverages',
        'fine_class': 'Coffee & Tea',
        'cost_price': '4.80',
        'inventory': 1800,
        'monthly_sales': 870,
    },
    {
        'sku_id': 'FOD-003',
        'product_name': 'Mixed Nuts Variety Pack Salted 24oz',
        'large_class': 'Food & Beverages',
        'fine_class': 'Snacks',
        'cost_price': '6.50',
        'inventory': 1500,
        'monthly_sales': 720,
    },
    {
        'sku_id': 'FOD-004',
        'product_name': 'Greek Yogurt Plain Non-Fat 32oz',
        'large_class': 'Food & Beverages',
        'fine_class': 'Dairy Products',
        'cost_price': '2.75',
        'inventory': 900,
        'monthly_sales': 650,
    },
    {
        'sku_id': 'FOD-005',
        'product_name': 'Extra Virgin Olive Oil 34oz',
        'large_class': 'Food & Beverages',
        'fine_class': 'Cooking Oils',
        'cost_price': '7.40',
        'inventory': 1100,
        'monthly_sales': 480,
    },
    {
        'sku_id': 'FOD-006',
        'product_name': 'Protein Powder Whey Chocolate 5lb',
        'large_class': 'Food & Beverages',
        'fine_class': 'Sports Nutrition',
        'cost_price': '28.00',
        'inventory': 650,
        'monthly_sales': 290,
    },
    {
        'sku_id': 'FOD-007',
        'product_name': 'Sparkling Water Variety Pack 12 Cans',
        'large_class': 'Food & Beverages',
        'fine_class': 'Beverages',
        'cost_price': '4.10',
        'inventory': 3200,
        'monthly_sales': 1800,
    },
    {
        'sku_id': 'FOD-008',
        'product_name': 'Dark Chocolate Bar 70% Cacao 3.5oz',
        'large_class': 'Food & Beverages',
        'fine_class': 'Candy & Chocolate',
        'cost_price': '1.85',
        'inventory': 2800,
        'monthly_sales': 1400,
    },
    {
        'sku_id': 'FOD-009',
        'product_name': 'Organic Almond Butter Smooth 16oz',
        'large_class': 'Food & Beverages',
        'fine_class': 'Nut Butters',
        'cost_price': '5.90',
        'inventory': 1200,
        'monthly_sales': 540,
    },
    {
        'sku_id': 'FOD-010',
        'product_name': 'Green Tea Bags Organic 100 Count',
        'large_class': 'Food & Beverages',
        'fine_class': 'Coffee & Tea',
        'cost_price': '3.60',
        'inventory': 2100,
        'monthly_sales': 960,
    },

    # ---- Clothing & Apparel（服装，10 条，CLO-001 ~ CLO-010）----
    {
        'sku_id': 'CLO-001',
        'product_name': "Women's Athletic Running Leggings High Waist",
        'large_class': 'Clothing & Apparel',
        'fine_class': "Women's Activewear",
        'cost_price': '9.80',
        'inventory': 680,
        'monthly_sales': 285,
    },
    {
        'sku_id': 'CLO-002',
        'product_name': "Men's Classic Fit Polo Shirt Short Sleeve",
        'large_class': 'Clothing & Apparel',
        'fine_class': "Men's Shirts",
        'cost_price': '8.50',
        'inventory': 920,
        'monthly_sales': 340,
    },
    {
        'sku_id': 'CLO-003',
        'product_name': 'Unisex Fleece Zip-Up Hoodie Sweatshirt',
        'large_class': 'Clothing & Apparel',
        'fine_class': 'Hoodies & Sweatshirts',
        'cost_price': '14.20',
        'inventory': 540,
        'monthly_sales': 210,
    },
    {
        'sku_id': 'CLO-004',
        'product_name': "Women's Floral Wrap Midi Dress Summer",
        'large_class': 'Clothing & Apparel',
        'fine_class': "Women's Dresses",
        'cost_price': '12.30',
        'inventory': 390,
        'monthly_sales': 145,
    },
    {
        'sku_id': 'CLO-005',
        'product_name': "Men's Slim Fit Chino Pants",
        'large_class': 'Clothing & Apparel',
        'fine_class': "Men's Pants",
        'cost_price': '16.00',
        'inventory': 720,
        'monthly_sales': 260,
    },
    {
        'sku_id': 'CLO-006',
        'product_name': "Kids' Rain Jacket Waterproof Windbreaker",
        'large_class': 'Clothing & Apparel',
        'fine_class': "Children's Outerwear",
        'cost_price': '11.50',
        'inventory': 460,
        'monthly_sales': 175,
    },
    {
        'sku_id': 'CLO-007',
        'product_name': "Women's Sports Bra High Impact Support",
        'large_class': 'Clothing & Apparel',
        'fine_class': "Women's Activewear",
        'cost_price': '7.60',
        'inventory': 810,
        'monthly_sales': 355,
    },
    {
        'sku_id': 'CLO-008',
        'product_name': "Men's Crew Neck Basic T-Shirt 3-Pack",
        'large_class': 'Clothing & Apparel',
        'fine_class': "Men's T-Shirts",
        'cost_price': '10.20',
        'inventory': 1350,
        'monthly_sales': 620,
    },
    {
        'sku_id': 'CLO-009',
        'product_name': 'Wool Blend Winter Scarf Plaid Pattern',
        'large_class': 'Clothing & Apparel',
        'fine_class': 'Scarves & Wraps',
        'cost_price': '5.40',
        'inventory': 580,
        'monthly_sales': 120,
    },
    {
        'sku_id': 'CLO-010',
        'product_name': "Men's Waterproof Hiking Boots Mid-Ankle",
        'large_class': 'Clothing & Apparel',
        'fine_class': "Men's Footwear",
        'cost_price': '38.00',
        'inventory': 320,
        'monthly_sales': 88,
    },

    # ---- Home & Kitchen（家居厨房，10 条，HOM-001 ~ HOM-010）----
    {
        'sku_id': 'HOM-001',
        'product_name': '12-Cup Programmable Drip Coffee Maker',
        'large_class': 'Home & Kitchen',
        'fine_class': 'Coffee Makers',
        'cost_price': '28.50',
        'inventory': 380,
        'monthly_sales': 145,
    },
    {
        'sku_id': 'HOM-002',
        'product_name': 'Non-Stick Ceramic Frying Pan Set 3-Piece',
        'large_class': 'Home & Kitchen',
        'fine_class': 'Cookware',
        'cost_price': '22.00',
        'inventory': 560,
        'monthly_sales': 210,
    },
    {
        'sku_id': 'HOM-003',
        'product_name': 'Robot Vacuum Cleaner Auto Charge Mapping',
        'large_class': 'Home & Kitchen',
        'fine_class': 'Vacuum Cleaners',
        'cost_price': '95.00',
        'inventory': 140,
        'monthly_sales': 48,
    },
    {
        'sku_id': 'HOM-004',
        'product_name': 'Egyptian Cotton Bath Towel Set 6-Piece',
        'large_class': 'Home & Kitchen',
        'fine_class': 'Bath Linens',
        'cost_price': '18.40',
        'inventory': 720,
        'monthly_sales': 290,
    },
    {
        'sku_id': 'HOM-005',
        'product_name': 'Stainless Steel Insulated Water Bottle 32oz',
        'large_class': 'Home & Kitchen',
        'fine_class': 'Drinkware',
        'cost_price': '8.75',
        'inventory': 1200,
        'monthly_sales': 580,
    },
    {
        'sku_id': 'HOM-006',
        'product_name': 'Bamboo Cutting Board Set with Juice Groove',
        'large_class': 'Home & Kitchen',
        'fine_class': 'Kitchen Tools',
        'cost_price': '12.60',
        'inventory': 850,
        'monthly_sales': 320,
    },
    {
        'sku_id': 'HOM-007',
        'product_name': 'Air Fryer 5.8 Quart Digital Touch Screen',
        'large_class': 'Home & Kitchen',
        'fine_class': 'Small Appliances',
        'cost_price': '48.00',
        'inventory': 275,
        'monthly_sales': 110,
    },
    {
        'sku_id': 'HOM-008',
        'product_name': 'Microfiber Bed Sheet Set Queen Size 4-Piece',
        'large_class': 'Home & Kitchen',
        'fine_class': 'Bed Linens',
        'cost_price': '14.50',
        'inventory': 680,
        'monthly_sales': 255,
    },
    {
        'sku_id': 'HOM-009',
        'product_name': 'Glass Food Storage Containers with Lids 10-Set',
        'large_class': 'Home & Kitchen',
        'fine_class': 'Food Storage',
        'cost_price': '16.80',
        'inventory': 920,
        'monthly_sales': 390,
    },
    {
        'sku_id': 'HOM-010',
        'product_name': 'Electric Kettle 1.7L Fast Boil Stainless Steel',
        'large_class': 'Home & Kitchen',
        'fine_class': 'Small Appliances',
        'cost_price': '19.20',
        'inventory': 490,
        'monthly_sales': 195,
    },

    # ---- Sports & Outdoors（运动户外，10 条，SPT-001 ~ SPT-010）----
    {
        'sku_id': 'SPT-001',
        'product_name': 'Yoga Mat Non-Slip 6mm Thick Extra Wide',
        'large_class': 'Sports & Outdoors',
        'fine_class': 'Yoga & Pilates',
        'cost_price': '11.00',
        'inventory': 960,
        'monthly_sales': 440,
    },
    {
        'sku_id': 'SPT-002',
        'product_name': 'Adjustable Dumbbell Set 5-50 lbs',
        'large_class': 'Sports & Outdoors',
        'fine_class': 'Strength Training',
        'cost_price': '120.00',
        'inventory': 85,
        'monthly_sales': 28,
    },
    {
        'sku_id': 'SPT-003',
        'product_name': 'Resistance Bands Set 5 Levels Loop Bands',
        'large_class': 'Sports & Outdoors',
        'fine_class': 'Fitness Accessories',
        'cost_price': '5.20',
        'inventory': 1800,
        'monthly_sales': 890,
    },
    {
        'sku_id': 'SPT-004',
        'product_name': 'Folding Camping Chair Portable Lightweight',
        'large_class': 'Sports & Outdoors',
        'fine_class': 'Camping Furniture',
        'cost_price': '14.50',
        'inventory': 520,
        'monthly_sales': 195,
    },
    {
        'sku_id': 'SPT-005',
        'product_name': 'Mountain Bike Helmet MIPS Safety Certified',
        'large_class': 'Sports & Outdoors',
        'fine_class': 'Cycling',
        'cost_price': '32.00',
        'inventory': 290,
        'monthly_sales': 105,
    },
    {
        'sku_id': 'SPT-006',
        'product_name': 'Foam Roller High Density for Muscle Recovery',
        'large_class': 'Sports & Outdoors',
        'fine_class': 'Fitness Accessories',
        'cost_price': '7.80',
        'inventory': 1100,
        'monthly_sales': 520,
    },
    {
        'sku_id': 'SPT-007',
        'product_name': 'Trekking Poles Carbon Fiber Collapsible Pair',
        'large_class': 'Sports & Outdoors',
        'fine_class': 'Hiking',
        'cost_price': '25.00',
        'inventory': 340,
        'monthly_sales': 118,
    },
    {
        'sku_id': 'SPT-008',
        'product_name': 'Basketball Spalding Official Size 7 Indoor',
        'large_class': 'Sports & Outdoors',
        'fine_class': 'Team Sports',
        'cost_price': '18.00',
        'inventory': 450,
        'monthly_sales': 170,
    },
    {
        'sku_id': 'SPT-009',
        'product_name': 'Waterproof Dry Bag 20L for Kayaking Camping',
        'large_class': 'Sports & Outdoors',
        'fine_class': 'Water Sports',
        'cost_price': '9.50',
        'inventory': 680,
        'monthly_sales': 245,
    },
    {
        'sku_id': 'SPT-010',
        'product_name': 'Jump Rope Speed Cable Adjustable Steel Wire',
        'large_class': 'Sports & Outdoors',
        'fine_class': 'Fitness Accessories',
        'cost_price': '4.30',
        'inventory': 2200,
        'monthly_sales': 1050,
    },
]


class Command(BaseCommand):
    help = (
        '将 50 条示例 SKU 数据（含向量嵌入）导入 Product 表。'
        '幂等：可安全多次执行（使用 update_or_create）。'
        '使用 --clear 参数可先清空再导入。'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='导入前先删除所有现有 Product 记录。',
        )

    def handle(self, *args, **options):
        # ---- 导入放在 handle() 内，避免模块加载时 AppRegistryNotReady ----
        from pricing.models import Product
        from sentence_transformers import SentenceTransformer

        # ---- 可选：清空现有数据 ----
        if options['clear']:
            count = Product.objects.count()
            Product.objects.all().delete()
            self.stdout.write(
                self.style.WARNING(f'已清空 {count} 条现有 Product 记录。')
            )

        # ---- 加载 Embedding 模型 ----
        model_name = getattr(settings, 'SENTENCE_TRANSFORMERS_MODEL', 'all-MiniLM-L6-v2')
        self.stdout.write(f'正在加载 sentence-transformers 模型：{model_name} ...')
        model = SentenceTransformer(model_name)
        self.stdout.write(self.style.SUCCESS('模型加载完成。'))
        self.stdout.write('')

        # ---- 逐条处理 SKU ----
        created_count = 0
        updated_count = 0
        total = len(SAMPLE_SKUS)

        for i, sku_data in enumerate(SAMPLE_SKUS, start=1):
            sku_id = sku_data['sku_id']
            product_name = sku_data['product_name']
            large_class = sku_data['large_class']
            fine_class = sku_data['fine_class']

            # Embedding 文本格式与 KnowledgeBaseAgent._vector_search 的 query_text 保持一致
            embed_text = f"{sku_id} {product_name} {large_class} {fine_class}"
            embedding_vector = model.encode(embed_text).tolist()

            product, created = Product.objects.update_or_create(
                sku_id=sku_id,
                defaults={
                    'product_name': product_name,
                    'large_class': large_class,
                    'fine_class': fine_class,
                    'cost_price': sku_data['cost_price'],
                    'inventory': sku_data['inventory'],
                    'monthly_sales': sku_data['monthly_sales'],
                    'embedding': embedding_vector,
                },
            )

            if created:
                created_count += 1
                status_label = self.style.SUCCESS('CREATED')
            else:
                updated_count += 1
                status_label = self.style.WARNING('UPDATED')

            self.stdout.write(
                f'  [{i:02d}/{total}] {status_label}: {sku_id} — {product_name}'
            )

        # ---- 汇总 ----
        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(
                f'完成。新增 {created_count} 条，更新 {updated_count} 条。'
                f'Product 表当前总记录数：{Product.objects.count()}'
            )
        )
