"""EMP-1/EMP-6: persona schema, the persona population, and system-prompt rendering."""
from pathlib import Path

from services.employee.personas.persona import (
    Persona,
    WhistleblowerTendency,
    load_persona,
    load_personas,
    temperature_for_risk,
)

_PERSONAS = Path(__file__).resolve().parent.parent / "personas"

_EXPECTED_IDS = {
    "EMP-QA-17", "PROD-WORKER-3", "PLANT-MGR-1", "CONCERNED-EMP-1", "WHISTLEBLOWER-1",
}


def test_qa_employee_yaml_loads():
    p = load_persona(_PERSONAS / "qa_employee.yaml")
    assert p.employee_id == "EMP-QA-17"
    assert p.title == "Quality Control Employee"
    assert p.whistleblower_tendency == WhistleblowerTendency.internal_only
    assert "REPORT_ISSUE" in p.authority.allowed_actions


def test_all_five_personas_load_with_distinct_ids():
    personas = load_personas(_PERSONAS)
    ids = [p.employee_id for p in personas]
    assert set(ids) == _EXPECTED_IDS
    assert len(ids) == len(set(ids))          # no duplicate ids


def test_temperature_follows_risk_band():
    for p in load_personas(_PERSONAS):
        risk = p.characteristics.get("risk_tolerance", "")
        assert p.temperature == temperature_for_risk(risk), p.employee_id


def test_personas_render_distinctly():
    by_id = {p.employee_id: p for p in load_personas(_PERSONAS)}
    # The whistleblower is the only one permitted to leak externally.
    wb = by_id["WHISTLEBLOWER-1"].render_system_prompt()
    assert "may leak information to external parties" in wb
    # The concerned employee is vocal and internal-only.
    concerned = by_id["CONCERNED-EMP-1"].render_system_prompt()
    assert "communication tendency: vocal" in concerned
    assert "never leak outside" in concerned.lower()
    # The plant manager still cannot exceed its authority.
    assert "cannot" in by_id["PLANT-MGR-1"].render_system_prompt().lower()


def test_system_prompt_contains_identity_authority_and_leak_rule():
    p = load_persona(_PERSONAS / "qa_employee.yaml")
    prompt = p.render_system_prompt()
    assert "Dana" in prompt and "Quality Control Employee" in prompt
    assert "EMP-QA-17" in prompt
    assert "compliance level: high" in prompt          # characteristic rendered
    assert "cannot stop the factory" in prompt.lower()  # authority ceiling stated
    assert "never leak outside" in prompt.lower()        # internal_only leak rule


def test_external_leak_tendency_changes_rule():
    p = Persona(
        employee_id="EMP-WB-1", display_name="Sam", title="Line Worker",
        goal="x", whistleblower_tendency=WhistleblowerTendency.external_leak,
    )
    assert "may leak information to external parties" in p.render_system_prompt()
