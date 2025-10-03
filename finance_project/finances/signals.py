from django.db.models.signals import post_save, pre_save, pre_delete
from django.dispatch import receiver
from decimal import Decimal
from .models import Transaction, Account
from django.db import transaction as db_transaction

@receiver(pre_save, sender=Transaction)
def adjust_balance_on_update(sender, instance: Transaction, **kwargs):
    """
    Handle balance adjustments when a transaction is created or updated.
    Strategy:
      - If creating: apply delta to account balance
      - If updating: compute old value and reverse it, then apply new value
    NOTE: This function reads old instance in DB (if exists).
    """
    if instance.pk is None:
        # new txn: we'll apply after save in post_save because we might need the txn to exist
        instance._adjustment = None
        return

    # existing transaction is being updated: compute delta
    try:
        old = Transaction.objects.get(pk=instance.pk)
    except Transaction.DoesNotExist:
        instance._adjustment = None
        return

    # compute old sign: income -> +amount, expense -> -amount
    def sign(tx):
        return Decimal('1') if tx.category.type == 'income' else Decimal('-1')

    old_effect = sign(old) * old.amount
    new_effect = sign(instance) * instance.amount

    instance._adjustment = {
        'account_id': instance.account_id,
        'delta': new_effect - old_effect
    }

@receiver(post_save, sender=Transaction)
def apply_balance_on_create_or_update(sender, instance: Transaction, created, **kwargs):
    """
    Apply balance changes after transaction saved.
    """
    from decimal import Decimal
    def sign(tx):
        return Decimal('1') if tx.category.type == 'income' else Decimal('-1')

    if created:
        delta = sign(instance) * instance.amount
        # atomic update
        with db_transaction.atomic():
            Account.objects.filter(pk=instance.account_id).select_for_update()
            acc = Account.objects.get(pk=instance.account_id)
            acc.balance = (acc.balance or Decimal('0')) + delta
            acc.save(update_fields=['balance'])
    else:
        # update case: instance._adjustment computed in pre_save
        adj = getattr(instance, '_adjustment', None)
        if adj and adj['delta'] != Decimal('0'):
            with db_transaction.atomic():
                acc = Account.objects.select_for_update().get(pk=adj['account_id'])
                acc.balance = (acc.balance or Decimal('0')) + adj['delta']
                acc.save(update_fields=['balance'])

@receiver(pre_delete, sender=Transaction)
def revert_balance_on_delete(sender, instance: Transaction, **kwargs):
    """
    Reverse the transaction effect on delete.
    """
    from decimal import Decimal
    def sign(tx):
        return Decimal('1') if tx.category.type == 'income' else Decimal('-1')

    delta = sign(instance) * instance.amount
    with db_transaction.atomic():
        acc = Account.objects.select_for_update().get(pk=instance.account_id)
        acc.balance = (acc.balance or Decimal('0')) - delta
        acc.save(update_fields=['balance'])
