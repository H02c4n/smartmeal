"""Order read queries. Object scope lives here: a customer's queryset only ever holds their own."""

from django.db.models import QuerySet

from apps.accounts.roles import Perm

from .models import CustomerAddress, Order


def _base() -> QuerySet[Order]:
    return Order.objects.select_related("customer").prefetch_related("lines", "events__actor")


def orders_visible_to(
    user, permissions: frozenset[str], *, for_cancel: bool = False
) -> QuerySet[Order]:
    """Everything for back-office roles, the user's own orders otherwise, nothing if neither.

    ``for_cancel`` widens "everything" to roles that may cancel any order.
    """
    see_all = Perm.ORDERS_CANCEL_ANY if for_cancel else Perm.ORDERS_READ_ALL
    if see_all in permissions:
        return _base()
    if Perm.ORDERS_PLACE in permissions:
        return _base().filter(customer=user)
    return Order.objects.none()


def filter_orders(queryset: QuerySet[Order], *, status=None, delivery_date=None, customer=None):
    if status:
        queryset = queryset.filter(status=status)
    if delivery_date:
        queryset = queryset.filter(delivery_date=delivery_date)
    if customer:
        queryset = queryset.filter(customer__email__iexact=customer.strip())
    return queryset


def addresses_of(user) -> QuerySet[CustomerAddress]:
    return CustomerAddress.objects.filter(user=user)
