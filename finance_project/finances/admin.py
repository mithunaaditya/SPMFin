from django.contrib import admin
from .models import Account, Category, Transaction, Budget

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('account_id', 'user', 'name', 'type', 'balance', 'updated_at')
    search_fields = ('name','user__username','user__email')

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('category_id','user','name','type','parent_category')
    search_fields = ('name', 'user__username')

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('txn_id','user','account','category','amount','txn_date','transfer_uuid')
    search_fields = ('description','user__username')
    list_filter = ('category', 'txn_date')

@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ('budget_id','user','category','account','amount','period_start','period_end')