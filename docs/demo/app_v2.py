"""Order service — pricing helpers."""

from dataclasses import dataclass

TAX_RATE = 0.19
FREE_SHIPPING_ABOVE = 50.0


@dataclass
class Order:
    sku: str
    quantity: int
    unit_price: float
    discount: float = 0.0


def subtotal(order: Order) -> float:
    gross = order.quantity * order.unit_price
    return gross * (1 - order.discount)


def shipping(order: Order) -> float:
    return 0.0 if subtotal(order) >= FREE_SHIPPING_ABOVE else 4.90


def total(order: Order) -> float:
    net = subtotal(order)
    return net + net * TAX_RATE + shipping(order)


def describe(order: Order) -> str:
    return f"{order.quantity} x {order.sku} = {total(order):.2f} EUR"
