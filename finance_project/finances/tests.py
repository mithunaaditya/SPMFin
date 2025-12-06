from decimal import Decimal
from datetime import date, timedelta
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from .models import Account, Category, Transaction, Budget


User = get_user_model()


class BaseModelTestCase(TestCase):
    def setUp(self):
        # Common user and base objects for all tests
        self.user = User.objects.create_user(
            username="testuser",
            password="password123"
        )

        self.other_user = User.objects.create_user(
            username="otheruser",
            password="password123"
        )

        self.cash_account = Account.objects.create(
            user=self.user,
            name="Cash Wallet",
            type="cash",
            balance=Decimal("100.00"),
        )

        self.bank_account = Account.objects.create(
            user=self.user,
            name="Bank Account",
            type="bank",
            balance=Decimal("500.00"),
        )

        self.income_category = Category.objects.create(
            user=self.user,
            name="Salary",
            type="income",
        )

        self.expense_category = Category.objects.create(
            user=self.user,
            name="Food",
            type="expense",
        )


class AccountModelTests(BaseModelTestCase):
    def test_account_creation(self):
        self.assertEqual(Account.objects.count(), 2)
        acc = self.cash_account
        self.assertEqual(acc.user, self.user)
        self.assertEqual(acc.name, "Cash Wallet")
        self.assertEqual(acc.type, "cash")
        self.assertEqual(acc.balance, Decimal("100.00"))
        self.assertIsNotNone(acc.created_at)
        self.assertIsNotNone(acc.updated_at)

    def test_account_str(self):
        s = str(self.cash_account)
        self.assertIn("Cash Wallet", s)
        self.assertIn("cash", s)

    def test_unique_account_name_per_user(self):
        # Same user + same name should fail
        with self.assertRaises(IntegrityError):
            Account.objects.create(
                user=self.user,
                name="Cash Wallet",
                type="cash",
            )

        # Different user can reuse same name
        acc = Account.objects.create(
            user=self.other_user,
            name="Cash Wallet",
            type="cash",
        )
        self.assertIsNotNone(acc.pk)

    def test_account_ordering_by_updated_at_desc(self):
        # Update one account and make sure it comes first
        self.cash_account.balance = Decimal("200.00")
        self.cash_account.save()

        accounts = list(Account.objects.all())
        self.assertEqual(accounts[0], self.cash_account)


class CategoryModelTests(BaseModelTestCase):
    def test_category_creation(self):
        self.assertEqual(Category.objects.count(), 2)
        cat = self.expense_category
        self.assertEqual(cat.user, self.user)
        self.assertEqual(cat.name, "Food")
        self.assertEqual(cat.type, "expense")
        self.assertIsNotNone(cat.created_at)
        self.assertIsNotNone(cat.updated_at)

    def test_category_str(self):
        s = str(self.income_category)
        self.assertIn("Salary", s)
        self.assertIn("income", s)

    def test_unique_category_name_per_user_and_type(self):
        # Same user + same name + same type should fail
        with self.assertRaises(IntegrityError):
            Category.objects.create(
                user=self.user,
                name="Food",
                type="expense",
            )

        # Different type with same name for same user is allowed
        other_type_cat = Category.objects.create(
            user=self.user,
            name="Food",
            type="income",
        )
        self.assertIsNotNone(other_type_cat.pk)

        # Different user with same name + type is allowed
        other_user_cat = Category.objects.create(
            user=self.other_user,
            name="Food",
            type="expense",
        )
        self.assertIsNotNone(other_user_cat.pk)

    def test_parent_child_relationship(self):
        parent = Category.objects.create(
            user=self.user,
            name="Transport",
            type="expense",
        )
        child = Category.objects.create(
            user=self.user,
            name="Bus",
            type="expense",
            parent_category=parent,
        )
        self.assertEqual(child.parent_category, parent)
        self.assertIn(child, parent.children.all())


class TransactionModelTests(BaseModelTestCase):
    def test_transaction_creation_basic(self):
        txn = Transaction.objects.create(
            user=self.user,
            account=self.cash_account,
            category=self.expense_category,
            amount=Decimal("50.00"),
            description="Lunch",
            txn_date=timezone.now(),
        )
        self.assertIsNotNone(txn.txn_id)
        self.assertIsNotNone(txn.created_at)
        self.assertIsNotNone(txn.updated_at)
        self.assertEqual(txn.user, self.user)
        self.assertEqual(txn.account, self.cash_account)
        self.assertEqual(txn.category, self.expense_category)

    def test_transaction_str(self):
        txn = Transaction.objects.create(
            user=self.user,
            account=self.cash_account,
            category=self.expense_category,
            amount=Decimal("10.00"),
        )
        s = str(txn)
        self.assertIn("Txn", s)
        self.assertIn(str(txn.txn_id), s)
        self.assertIn(str(self.user), s)

    def test_transaction_is_income_and_is_expense(self):
        income_txn = Transaction.objects.create(
            user=self.user,
            account=self.bank_account,
            category=self.income_category,
            amount=Decimal("1000.00"),
        )
        expense_txn = Transaction.objects.create(
            user=self.user,
            account=self.cash_account,
            category=self.expense_category,
            amount=Decimal("100.00"),
        )

        self.assertTrue(income_txn.is_income())
        self.assertFalse(income_txn.is_expense())
        self.assertTrue(expense_txn.is_expense())
        self.assertFalse(expense_txn.is_income())

    def test_transaction_clean_category_user_mismatch_raises(self):
        # Category belongs to other user
        other_cat = Category.objects.create(
            user=self.other_user,
            name="OtherFood",
            type="expense",
        )

        txn = Transaction(
            user=self.user,
            account=self.cash_account,
            category=other_cat,
            amount=Decimal("10.00"),
        )
        with self.assertRaises(ValueError):
            txn.clean()

    def test_transaction_clean_account_user_mismatch_raises(self):
        # Account belongs to other user
        other_acc = Account.objects.create(
            user=self.other_user,
            name="Other Account",
            type="cash",
        )

        txn = Transaction(
            user=self.user,
            account=other_acc,
            category=self.expense_category,
            amount=Decimal("10.00"),
        )
        with self.assertRaises(ValueError):
            txn.clean()

    def test_transaction_clean_passes_for_correct_user(self):
        txn = Transaction(
            user=self.user,
            account=self.cash_account,
            category=self.expense_category,
            amount=Decimal("10.00"),
        )
        # Should not raise
        txn.clean()

    def test_transfer_transactions_share_uuid(self):
        transfer_id = uuid4()

        debit_txn = Transaction.objects.create(
            user=self.user,
            account=self.cash_account,
            category=self.expense_category,
            amount=Decimal("100.00"),
            description="Transfer out",
            transfer_uuid=transfer_id,
        )

        credit_txn = Transaction.objects.create(
            user=self.user,
            account=self.bank_account,
            category=self.income_category,
            amount=Decimal("100.00"),
            description="Transfer in",
            transfer_uuid=transfer_id,
        )

        self.assertEqual(debit_txn.transfer_uuid, credit_txn.transfer_uuid)
        self.assertEqual(
            Transaction.objects.filter(transfer_uuid=transfer_id).count(), 2
        )

    def test_transaction_ordering_by_txn_date_desc(self):
        # older
        t1 = Transaction.objects.create(
            user=self.user,
            account=self.cash_account,
            category=self.expense_category,
            amount=Decimal("5.00"),
            txn_date=timezone.now() - timedelta(days=1),
        )
        # newer
        t2 = Transaction.objects.create(
            user=self.user,
            account=self.cash_account,
            category=self.expense_category,
            amount=Decimal("10.00"),
            txn_date=timezone.now(),
        )

        txns = list(Transaction.objects.filter(user=self.user))
        self.assertEqual(txns[0], t2)
        self.assertEqual(txns[1], t1)


class BudgetModelTests(BaseModelTestCase):
    def test_budget_creation(self):
        start = date.today()
        end = start + timedelta(days=30)

        budget = Budget.objects.create(
            user=self.user,
            category=self.expense_category,
            account=None,
            period_start=start,
            period_end=end,
            amount=Decimal("1000.00"),
        )

        self.assertIsNotNone(budget.budget_id)
        self.assertEqual(budget.user, self.user)
        self.assertEqual(budget.category, self.expense_category)
        self.assertIsNone(budget.account)
        self.assertEqual(budget.period_start, start)
        self.assertEqual(budget.period_end, end)

    def test_budget_str(self):
        start = date.today()
        end = start + timedelta(days=30)

        budget = Budget.objects.create(
            user=self.user,
            category=self.expense_category,
            period_start=start,
            period_end=end,
            amount=Decimal("500.00"),
        )

        s = str(budget)
        self.assertIn("Budget", s)
        self.assertIn("Food", s)
        self.assertIn(str(start), s)

    def test_budget_for_account_instead_of_category(self):
        start = date.today()
        end = start + timedelta(days=30)

        budget = Budget.objects.create(
            user=self.user,
            account=self.cash_account,
            category=None,
            period_start=start,
            period_end=end,
            amount=Decimal("300.00"),
        )

        self.assertEqual(budget.account, self.cash_account)
        self.assertIsNone(budget.category)

    def test_budget_period_constraint_invalid(self):
        """
        period_end < period_start should fail due to CheckConstraint.
        With Django's model validation, full_clean() should raise ValidationError.
        At DB level, an IntegrityError can also be raised if saved without validation.
        """
        start = date.today()
        end = start - timedelta(days=1)  # invalid

        budget = Budget(
            user=self.user,
            category=self.expense_category,
            period_start=start,
            period_end=end,
            amount=Decimal("100.00"),
        )

        # Model validation
        with self.assertRaises(ValidationError):
            budget.full_clean()

        # Direct save may raise IntegrityError depending on backend
        with self.assertRaises(IntegrityError):
            Budget.objects.create(
                user=self.user,
                category=self.expense_category,
                period_start=start,
                period_end=end,
                amount=Decimal("100.00"),
            )

    def test_budget_ordering_by_period_start_desc(self):
        start1 = date(2024, 1, 1)
        start2 = date(2024, 2, 1)

        b1 = Budget.objects.create(
            user=self.user,
            category=self.expense_category,
            period_start=start1,
            period_end=start1 + timedelta(days=30),
            amount=Decimal("100.00"),
        )
        b2 = Budget.objects.create(
            user=self.user,
            category=self.expense_category,
            period_start=start2,
            period_end=start2 + timedelta(days=30),
            amount=Decimal("200.00"),
        )

        budgets = list(Budget.objects.all())
        self.assertEqual(budgets[0], b2)
        self.assertEqual(budgets[1], b1)
