from django.db.models.signals import post_save, pre_save, pre_delete
from django.dispatch import receiver
from decimal import Decimal
from django.db import transaction as db_transaction
from .models import Transaction, Account, Category
from django.contrib.auth.models import User


@receiver(post_save, sender=User)
def create_default_transfer_categories(sender, instance, created, **kwargs):
    if created:
        # Create "Transfer In" category
        Category.objects.create(
            user=instance,
            name="Transfer In",
            type="income"
        )
        # Create "Transfer Out" category
        Category.objects.create(
            user=instance,
            name="Transfer Out",
            type="expense"
        )

def sign(tx):
    """Return +1 for income, -1 for expense"""
    return Decimal('1') if tx.category.type == 'income' else Decimal('-1')


@receiver(pre_save, sender=Transaction)
def adjust_balance_on_update(sender, instance: Transaction, **kwargs):
    """
    Compute balance adjustments for create or update.
    Supports normal and transfer transactions.
    """
    if instance.pk is None:
        # New transaction
        delta = sign(instance) * instance.amount
        instance._adjustment = {
            'old_account': None,
            'new_account': instance.account_id,
            'delta_old': Decimal('0'),
            'delta_new': delta
        }
        return

    # Existing transaction
    try:
        old = Transaction.objects.get(pk=instance.pk)
    except Transaction.DoesNotExist:
        instance._adjustment = None
        return

    # Determine if this is part of a transfer
    if old.transfer_uuid:
        # Get both transactions
        transfer_txns = Transaction.objects.filter(transfer_uuid=old.transfer_uuid, user=instance.user)
        if transfer_txns.count() != 2:
            instance._adjustment = None
            return

        # Identify outgoing (expense) and incoming (income)
        outgoing = transfer_txns.get(category__type='expense')
        incoming = transfer_txns.get(category__type='income')

        # Compute deltas
        outgoing_delta = sign(instance) * instance.amount - sign(outgoing) * outgoing.amount if instance.pk == outgoing.pk else Decimal('0')
        incoming_delta = sign(instance) * instance.amount - sign(incoming) * incoming.amount if instance.pk == incoming.pk else Decimal('0')

        instance._adjustment = {
            'transfer': True,
            'outgoing': {'account': outgoing.account_id, 'delta': outgoing_delta},
            'incoming': {'account': incoming.account_id, 'delta': incoming_delta}
        }
    else:
        # Normal transaction
        old_effect = sign(old) * old.amount
        new_effect = sign(instance) * instance.amount
        delta_old = -old_effect if old.account_id != instance.account_id else Decimal('0')
        delta_new = new_effect if old.account_id != instance.account_id else new_effect - old_effect
        instance._adjustment = {
            'transfer': False,
            'old_account': old.account_id if delta_old != 0 else None,
            'new_account': instance.account_id,
            'delta_old': delta_old,
            'delta_new': delta_new
        }


@receiver(post_save, sender=Transaction)
def apply_balance_on_create_or_update(sender, instance: Transaction, created, **kwargs):
    """Apply balance adjustments after save"""
    adj = getattr(instance, '_adjustment', None)
    if not adj:
        return

    with db_transaction.atomic():
        if adj.get('transfer'):
            # Transfer: update both outgoing and incoming
            out_acc = Account.objects.select_for_update().get(pk=adj['outgoing']['account'])
            out_acc.balance = (out_acc.balance or Decimal('0')) + adj['outgoing']['delta']
            out_acc.save(update_fields=['balance'])

            in_acc = Account.objects.select_for_update().get(pk=adj['incoming']['account'])
            in_acc.balance = (in_acc.balance or Decimal('0')) + adj['incoming']['delta']
            in_acc.save(update_fields=['balance'])
        else:
            # Normal transaction
            if adj.get('old_account'):
                old_acc = Account.objects.select_for_update().get(pk=adj['old_account'])
                old_acc.balance = (old_acc.balance or Decimal('0')) + adj['delta_old']
                old_acc.save(update_fields=['balance'])

            new_acc = Account.objects.select_for_update().get(pk=adj['new_account'])
            new_acc.balance = (new_acc.balance or Decimal('0')) + adj['delta_new']
            new_acc.save(update_fields=['balance'])


@receiver(pre_delete, sender=Transaction)
def revert_balance_on_delete(sender, instance: Transaction, **kwargs):
    """Reverse the transaction effect on delete"""
    with db_transaction.atomic():
        if instance.transfer_uuid:
            # Only process the transfer once, e.g., only for the outgoing transaction
            transfer_txns = Transaction.objects.filter(transfer_uuid=instance.transfer_uuid, user=instance.user)
            
            # Pick the outgoing (expense) transaction as the primary one
            outgoing = transfer_txns.filter(category__type='expense').first()
            if instance.pk != outgoing.pk:
                # Skip balance adjustment for incoming transaction
                return
            
            # Adjust both accounts
            for tx in transfer_txns:
                delta = sign(tx) * tx.amount
                acc = Account.objects.select_for_update().get(pk=tx.account_id)
                acc.balance = (acc.balance or Decimal('0')) - delta
                acc.save(update_fields=['balance'])
        else:
            # Normal transaction
            delta = sign(instance) * instance.amount
            acc = Account.objects.select_for_update().get(pk=instance.account_id)
            acc.balance = (acc.balance or Decimal('0')) - delta
            acc.save(update_fields=['balance'])