"""Order service — pricing helpers."""

from dataclasses import dataclass

TAX_RATE = 0.19


@dataclass
class Order:
    sku: str
    quantity: int
    unit_price: float


def subtotal(order: Order) -> float:
    return order.quantity * order.unit_price


def total(order: Order) -> float:
    net = subtotal(order)
    return net + net * TAX_RATE


def describe(order: Order) -> str:
    return f"{order.quantity} x {order.sku} = {total(order):.2f}"
