"""A tiny name -> instance registry.

Used as the Employee service's *profile registry* (employee_id -> EmployeeAgent),
and reusable anywhere a coordinator needs to resolve an actor by a stable key.
The key attribute is configurable so it works for agents keyed by `employee_id`,
`role`, `name`, etc.
"""
from __future__ import annotations

from typing import Generic, TypeVar

T = TypeVar("T")


class Registry(Generic[T]):
    def __init__(self, key: str = "name") -> None:
        self._key = key
        self._items: dict[str, T] = {}

    def register(self, item: T) -> None:
        self._items[getattr(item, self._key)] = item

    def get(self, name: str) -> T | None:
        return self._items.get(name)

    def names(self) -> list[str]:
        return list(self._items)

    def all(self) -> list[T]:
        return list(self._items.values())

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, name: str) -> bool:
        return name in self._items
