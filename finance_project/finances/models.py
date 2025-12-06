from django.db import models

# Create your models here.
from uuid import uuid4
from django.db import models, transaction as db_transaction
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from django.core.validators import MinValueValidator

User = get_user_model()

class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        abstract = True

class Account(models.Model):
    ACCOUNT_TYPES = [
        ('cash', 'Cash'),
        ('bank', 'Bank'),
        ('wallet', 'Wallet'),
        ('credit', 'Credit'),
        ('investment', 'Investment'),
        ('other', 'Other'),
    ]

    account_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='accounts')
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=50, choices=ACCOUNT_TYPES, default='other')
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'name')
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.name} ({self.user}) - {self.type} : {self.balance}"

class Category(models.Model):
    CATEGORY_TYPES = [
        ('income', 'Income'),
        ('expense', 'Expense'),
    ]

    category_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='categories')
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=20, choices=CATEGORY_TYPES)
    parent_category = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name="children")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'name', 'type')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.type})"

class Transaction(TimestampedModel):
    """
    A Transaction can be:
    - income or expense (category.type determines this)
    - transfer: represented by two Transaction rows sharing a transfer_uuid
      (one with negative effect, one with positive).
    """

    txn_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='transactions')
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='transactions')
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='transactions')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    txn_date = models.DateTimeField(default=timezone.now)
    receipt_image_url = models.CharField(max_length=255, blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)

    # transfer_uuid groups two transactions: debit from one account, credit to another
    transfer_uuid = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ['-txn_date', '-created_at']

    def clean(self):
        # ensure category.user == transaction.user (categories are per-user)
        if self.category.user_id != self.user_id:
            raise ValueError("Category must belong to the same user as the transaction.")
        if self.account.user_id != self.user_id:
            raise ValueError("Account must belong to the same user as the transaction.")

    def save(self, *args, **kwargs):
        """
        We'll adjust account balances in signals. We keep save() clean to allow bulk ops.
        """
        super().save(*args, **kwargs)

    def is_income(self):
        return self.category.type == 'income'

    def is_expense(self):
        return self.category.type == 'expense'

    def __str__(self):
        return f"Txn {self.txn_id} - {self.user} - {self.amount} on {self.txn_date}"


class Budget(models.Model):
    budget_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='budgets'
    )
    category = models.ForeignKey(
        'Category',
        on_delete=models.CASCADE,
        related_name='budgets'
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Prevent duplicate budgets for same user-category pair
        unique_together = ('user', 'category')
        ordering = ['-created_at']

    def __str__(self):
        return f"Budget ₹{self.amount} for {self.category.name}"