"""Unit tests for the profile/agent registry."""
from dataclasses import dataclass

from packages.agentkit.registry import Registry


@dataclass
class _Agent:
    employee_id: str
    label: str


def test_register_and_get_by_custom_key():
    reg: Registry[_Agent] = Registry(key="employee_id")
    a = _Agent("EMP-QA-17", "Dana")
    reg.register(a)
    assert reg.get("EMP-QA-17") is a
    assert reg.get("missing") is None


def test_names_all_and_contains():
    reg: Registry[_Agent] = Registry(key="employee_id")
    reg.register(_Agent("EMP-1", "x"))
    reg.register(_Agent("EMP-2", "y"))
    assert set(reg.names()) == {"EMP-1", "EMP-2"}
    assert len(reg) == 2
    assert "EMP-1" in reg
    assert {a.label for a in reg.all()} == {"x", "y"}
