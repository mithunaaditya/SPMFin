from rest_framework.routers import DefaultRouter
from . import views
from django.urls import path, include

router = DefaultRouter()
router.register(r'accounts', views.AccountViewSet, basename='account')
router.register(r'categories', views.CategoryViewSet, basename='category')
router.register(r'transactions', views.TransactionViewSet, basename='transaction')
router.register(r'budgets', views.BudgetViewSet, basename='budget')
router.register(r'reports', views.ReportViewSet, basename='report')



urlpatterns = [
    path('', include(router.urls)),

    # Auth endpoints
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/', views.login_view, name='login'),
]