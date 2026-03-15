from django.urls import path
from .views import PricingUploadView, PricingDetailView, PricingDownloadView

urlpatterns = [
    path('pricing/upload/', PricingUploadView.as_view(), name='pricing-upload'),
    path('pricing/<uuid:request_id>/', PricingDetailView.as_view(), name='pricing-detail'),
    path('pricing/<uuid:request_id>/download/', PricingDownloadView.as_view(), name='pricing-download'),
]
