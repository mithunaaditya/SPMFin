# tests.py
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from .models import Account, Category, Transaction, Budget


User = get_user_model()


class BaseModelTestCase(TestCase):
    """
    Common setup for all model tests: create two users, some accounts and categories.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="user1",
            email="user1@example.com",
            password="password123",
        )
        self.other_user = User.objects.create_user(
            username="user2",
            email="user2@example.com",
            password="password123",
        )

        # Accounts for self.user
        self.cash_account = Account.objects.create(
            user=self.user,
            name="Cash",
            type="cash",
            balance=Decimal("1000.00"),
        )
        self.bank_account = Account.objects.create(
            user=self.user,
            name="Bank",
            type="bank",
            balance=Decimal("5000.00"),
        )

        # Categories for self.user
        self.salary_category = Category.objects.create(
            user=self.user,
            name="Salary",
            type="income",
        )
        self.food_category = Category.objects.create(
            user=self.user,
            name="Food",
            type="expense",
        )


class AccountModelTests(BaseModelTestCase):
    def test_account_str(self):
        self.assertIn("Cash", str(self.cash_account))
        self.assertIn("cash", str(self.cash_account))

    def test_account_name_unique_per_user(self):
        Account.objects.create(
            user=self.user,
            name="Wallet",
            type="wallet",
            balance=Decimal("0.00"),
        )
        # Same user + same name should violate unique_together
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Account.objects.create(
                    user=self.user,
                    name="Wallet",
                    type="wallet",
                    balance=Decimal("10.00"),
                )

    def test_account_name_can_repeat_for_different_users(self):
        Account.objects.create(
            user=self.user,
            name="SharedName",
            type="cash",
        )
        # Different user, same name is allowed
        try:
            Account.objects.create(
                user=self.other_user,
                name="SharedName",
                type="cash",
            )
        except IntegrityError:
            self.fail("Account name should be unique per user, not globally.")


class CategoryModelTests(BaseModelTestCase):
    def test_category_str(self):
        self.assertEqual(str(self.salary_category), "Salary (income)")
        self.assertEqual(str(self.food_category), "Food (expense)")

    def test_category_unique_per_user_and_type(self):
        Category.objects.create(
            user=self.user,
            name="Shopping",
            type="expense",
        )
        # Same user + same name + same type -> violation
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Category.objects.create(
                    user=self.user,
                    name="Shopping",
                    type="expense",
                )

    def test_category_name_can_repeat_with_different_type(self):
        # Same user + same name but different type is allowed
        Category.objects.create(
            user=self.user,
            name="Bonus",
            type="income",
        )
        try:
            Category.objects.create(
                user=self.user,
                name="Bonus",
                type="expense",
            )
        except IntegrityError:
            self.fail("Category should be unique by (user, name, type).")

    def test_parent_category_optional(self):
        sub_category = Category.objects.create(
            user=self.user,
            name="Groceries",
            type="expense",
            parent_category=self.food_category,
        )
        self.assertEqual(sub_category.parent_category, self.food_category)


class TransactionModelTests(BaseModelTestCase):
    def test_transaction_creation_valid(self):
        txn = Transaction.objects.create(
            user=self.user,
            account=self.cash_account,
            category=self.food_category,
            amount=Decimal("100.00"),
            description="Dinner",
            txn_date=timezone.now(),
        )
        self.assertIsNotNone(txn.txn_id)
        self.assertEqual(txn.user, self.user)
        self.assertEqual(txn.account, self.cash_account)
        self.assertEqual(txn.category, self.food_category)

    def test_is_income_and_is_expense(self):
        income_txn = Transaction.objects.create(
            user=self.user,
            account=self.bank_account,
            category=self.salary_category,  # income
            amount=Decimal("10000.00"),
        )
        expense_txn = Transaction.objects.create(
            user=self.user,
            account=self.cash_account,
            category=self.food_category,  # expense
            amount=Decimal("250.00"),
        )

        self.assertTrue(income_txn.is_income())
        self.assertFalse(income_txn.is_expense())

        self.assertTrue(expense_txn.is_expense())
        self.assertFalse(expense_txn.is_income())

    def test_clean_raises_if_category_belongs_to_different_user(self):
        other_user_category = Category.objects.create(
            user=self.other_user,
            name="Other Food",
            type="expense",
        )
        txn = Transaction(
            user=self.user,
            account=self.cash_account,
            category=other_user_category,
            amount=Decimal("50.00"),
        )
        with self.assertRaises(ValueError) as ctx:
            txn.clean()

        self.assertIn("Category must belong to the same user", str(ctx.exception))

    def test_clean_raises_if_account_belongs_to_different_user(self):
        other_user_account = Account.objects.create(
            user=self.other_user,
            name="Other Cash",
            type="cash",
        )
        txn = Transaction(
            user=self.user,
            account=other_user_account,
            category=self.food_category,
            amount=Decimal("50.00"),
        )
        with self.assertRaises(ValueError) as ctx:
            txn.clean()

        self.assertIn("Account must belong to the same user", str(ctx.exception))

    def test_transfer_uuid_groups_transactions(self):
        transfer_id = "12345678-1234-5678-1234-567812345678"

        t1 = Transaction.objects.create(
            user=self.user,
            account=self.cash_account,
            category=self.food_category,
            amount=Decimal("500.00"),
            transfer_uuid=transfer_id,
        )
        t2 = Transaction.objects.create(
            user=self.user,
            account=self.bank_account,
            category=self.food_category,
            amount=Decimal("-500.00"),
            transfer_uuid=transfer_id,
        )

        grouped = Transaction.objects.filter(transfer_uuid=transfer_id)
        self.assertEqual(grouped.count(), 2)
        self.assertIn(t1, grouped)
        self.assertIn(t2, grouped)