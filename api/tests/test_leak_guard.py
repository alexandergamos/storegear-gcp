"""The output guardrail, offline: tool names and prompt wording never reach the user (replaces the live internal-tools probe)."""
import guards


def test_tool_names_in_an_answer_are_a_leak():
    assert guards.leak("Uso buscar_catalogo_hibrido y consultar_precio_stock para responder.") == "term:buscar_catalogo_hibrido"


def test_an_ordinary_answer_is_not_a_leak():
    assert guards.leak("El Polar Ignite 2 pesa 35 g y es resistente al agua hasta 30 metros.") is None
