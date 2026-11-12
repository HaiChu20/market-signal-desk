from msd.research.method_registry import load_registry, reconciliation


def test_documented_registry_reconciles_to_protocol_units():
    registry = load_registry()
    summary = reconciliation(registry)
    assert summary == {
        "documented_table_rows": 30,
        "pilot_modules": 3,
        "detector_modules": 33,
        "multi_variant_expansion": 2,
        "tournament_units": 35,
        "inputs_pending": 1,
    }
    assert {spec.key for spec in registry if spec.name == "bollinger"} == {
        "bollinger:band_reversion", "bollinger:squeeze_breakout"}
    assert {spec.key for spec in registry if spec.name == "post_macro_event_reaction"} == {
        "post_macro_event_reaction:follow", "post_macro_event_reaction:fade"}
    pending = [spec for spec in registry if spec.status == "inputs_pending"]
    assert [(spec.id, spec.name) for spec in pending] == [(34, "post_earnings_index_reaction")]
