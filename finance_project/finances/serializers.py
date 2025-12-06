from rest_framework import serializers
from .models import Account, Category, Transaction, Budget
from decimal import Decimal
from django.utils import timezone
import uuid
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password

class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = ['account_id','user','name','type','balance','created_at','updated_at']
        read_only_fields = ['balance','created_at','updated_at','user']  # user is auto-set

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['category_id','user','name','type','parent_category','created_at','updated_at']
        read_only_fields = ['user', 'created_at', 'updated_at']

class TransactionSerializer(serializers.ModelSerializer):
    """
    When creating a transfer, client may pass:
      {
        "transfer": {
           "to_account": <account_id>,
           "amount": 100.00,
           "description": "Transfer to savings"
        }
      }
    For transfers, server will create two Transaction rows with same transfer_uuid.
    """
    transfer = serializers.JSONField(write_only=True, required=False, help_text="Optional transfer dict when creating transfer")
    class Meta:
        model = Transaction
        fields = [
            'txn_id','user','account','category','amount','description','txn_date',
            'receipt_image_url','location','transfer_uuid','transfer',
            'created_at','updated_at'
        ]
        read_only_fields = ['user','transfer_uuid','created_at','updated_at']

    def validate(self, attrs):
        # ensure category belongs to user
        user = self.context['request'].user
        category = attrs.get('category')
        account = attrs.get('account')
        if category and category.user_id != user.id:
            raise serializers.ValidationError("Category must belong to the same user.")
        if account and account.user_id != user.id:
            raise serializers.ValidationError("Account must belong to the same user.")
        return attrs

    def create(self, validated_data):
        transfer_info = validated_data.pop('transfer', None)
        if transfer_info:
            # create transfer: debit from account (expense) and credit to to_account (income)
            # We require that category provided is of type 'expense' for debit, and for the destination we choose an 'income' category
            from .models import Transaction, Category, Account
            to_account_id = transfer_info.get('to_account')
            amount = Decimal(validated_data['amount'])
            description = validated_data.get('description', '')
            user = validated_data['user']
            from_account = validated_data['account']
            to_account = Account.objects.get(pk=to_account_id)

            # ensure same user
            if to_account.user_id != user.id:
                raise serializers.ValidationError("Destination account must belong to the same user.")

            # create a shared UUID
            transfer_uuid = uuid.uuid4()

            # For the transfer we need categories that reflect expense and income.
            # Expectation: caller passes a category for the outgoing (expense) side.
            outgoing_category = validated_data['category']
            if outgoing_category.type != 'expense':
                raise serializers.ValidationError("Category for outgoing side must be an 'expense' category.")

            # For the incoming side: find or create a generic 'Transfer In' income category for the user
            income_cat, _ = Category.objects.get_or_create(
                user=user, name='Transfer In', type='income', defaults={'parent_category': None}
            )

            # create outgoing txn (expense)
            outgoing = Transaction.objects.create(
                user=user,
                account=from_account,
                category=outgoing_category,
                amount=amount,
                description=description,
                txn_date=validated_data.get('txn_date', timezone.now()),
                transfer_uuid=transfer_uuid
            )

            # create incoming txn (income) to destination account
            incoming = Transaction.objects.create(
                user=user,
                account=to_account,
                category=income_cat,
                amount=amount,
                description=f"Transfer from {from_account.name}: {description}",
                txn_date=validated_data.get('txn_date', timezone.now()),
                transfer_uuid=transfer_uuid
            )

            # return one of them (outgoing) as the created object
            return outgoing

        # not a transfer: normal transaction
        return super().create(validated_data)
    
    

class BudgetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Budget
        fields = ['budget_id', 'user', 'category', 'amount', 'created_at', 'updated_at']
        read_only_fields = ['user', 'created_at', 'updated_at']

    def validate(self, attrs):
        user = self.context['request'].user
        category = attrs.get('category')

        # ensure category belongs to the same user
        if category and category.user_id != user.id:
            raise serializers.ValidationError("Category must belong to the logged-in user.")
        return attrs



class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'password2')

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Passwords do not match"})
        return attrs

    def create(self, validated_data):
        user = User.objects.create(
            username=validated_data['username'],
            email=validated_data['email'],
        )
        user.set_password(validated_data['password'])
        user.save()
        return user

class ReportSerializer(serializers.ModelSerializer):
    total_amount = serializers.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        model = Category
        fields = ['category_id', 'name', 'type', 'total_amount']