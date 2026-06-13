from business_card_watchdog.sinks import (
    build_sink_adapter_request,
    build_sink_apply_decision,
    build_sink_apply_preflight,
    build_sink_apply_result,
    build_sink_lookup_plan,
    build_sink_lookup_result,
    build_sink_plan,
    build_sink_payloads,
    canonical_contact_fingerprint,
    check_sink_readiness,
    contact_serialization_key,
)


def test_fingerprint_is_stable_across_whitespace() -> None:
    left = canonical_contact_fingerprint(
        {
            "full_name": "Ada   Lovelace",
            "email": " ada@example.test ",
            "phone": "+1 555 0100",
        }
    )
    right = canonical_contact_fingerprint(
        {
            "full_name": "Ada Lovelace",
            "email": "ada@example.test",
            "phone": "+1 555 0100",
        }
    )

    assert left == right


def test_dry_run_readiness_does_not_require_credentials() -> None:
    readiness = check_sink_readiness("google_contacts", dry_run=True)

    assert readiness.ready
    assert "dry-run" in readiness.reason


def test_live_readiness_blocks_when_apply_disabled() -> None:
    readiness = check_sink_readiness("odoo", dry_run=False)

    assert not readiness.ready
    assert readiness.status == "blocked"
    assert "disabled" in readiness.reason


def test_live_odoo_readiness_is_blocked_until_implemented_when_apply_enabled() -> None:
    readiness = check_sink_readiness("odoo", dry_run=False, apply_enabled=True)

    assert not readiness.ready
    assert readiness.status == "blocked"
    assert "not implemented" in readiness.reason


def test_build_sink_payloads_include_match_keys_and_readiness() -> None:
    payloads = build_sink_payloads(
        sinks=["google_contacts", "odoo"],
        spec={"full_name": "Ada Lovelace", "email": "ada@example.test"},
        dry_run=True,
    )

    assert [payload.sink for payload in payloads] == ["google_contacts", "odoo"]
    assert all(payload.state == "dry_run" for payload in payloads)
    assert all(payload.match_keys["email"] == "ada@example.test" for payload in payloads)
    assert payloads[0].fingerprint == payloads[1].fingerprint
    assert payloads[0].serialization_key == "email:ada@example.test"


def test_build_sink_plan_is_dry_run_and_action_oriented() -> None:
    plan = build_sink_plan(
        sinks=["google_contacts", "odoo"],
        spec={"full_name": "Ada Lovelace", "email": "ada@example.test"},
        dry_run=True,
        reason="matched email_domain=*",
    )

    assert plan["schema"] == "business-card-watchdog.sink-plan.v1"
    assert plan["state"] == "dry_run"
    assert [action["sink"] for action in plan["actions"]] == ["google_contacts", "odoo"]
    assert all(action["action"] == "plan_upsert" for action in plan["actions"])


def test_build_sink_lookup_plan_is_zero_network_and_keyed() -> None:
    plan = build_sink_lookup_plan(
        sinks=["google_contacts", "odoo"],
        spec={"full_name": "Ada Lovelace", "email": "ada@example.test", "phone": "+15550101234"},
        dry_run=True,
        reason="matched email_domain=*",
    )

    assert plan["schema"] == "business-card-watchdog.sink-lookup-plan.v1"
    assert plan["state"] == "dry_run"
    assert plan["network_calls_made"] == 0
    assert {lookup["sink"] for lookup in plan["lookups"]} == {"google_contacts", "odoo"}
    assert all(lookup["readiness"]["status"] == "ready" for lookup in plan["lookups"])
    assert plan["lookups"][0]["match_keys"]["email"] == "ada@example.test"
    assert any(query["field"] == "email" for query in plan["lookups"][0]["queries"])


def test_build_sink_adapter_request_prepares_lookup_write_and_readback_contracts() -> None:
    lookup_plan = build_sink_lookup_plan(
        sinks=["google_contacts", "odoo"],
        spec={"full_name": "Ada Lovelace", "email": "ada@example.test"},
        dry_run=True,
        reason="matched email_domain=*",
    )
    sink_plan = build_sink_plan(
        sinks=["google_contacts", "odoo"],
        spec={"full_name": "Ada Lovelace", "email": "ada@example.test"},
        dry_run=True,
        reason="matched email_domain=*",
    )
    preflight = build_sink_apply_preflight(plan=sink_plan, apply=False)
    decision = build_sink_apply_decision(preflight=preflight, decision="approve", reviewer="operator")
    apply_result = build_sink_apply_result(preflight=preflight, decision=decision, apply=True, simulate=True)

    lookup = build_sink_adapter_request(phase="lookup", lookup_plan=lookup_plan)
    write = build_sink_adapter_request(phase="write", sink_plan=sink_plan)
    readback = build_sink_adapter_request(phase="readback", apply_result=apply_result)

    assert lookup["schema"] == "business-card-watchdog.sink-adapter-request.v1"
    assert lookup["phase"] == "lookup"
    assert lookup["network_calls_made"] == 0
    assert lookup["writes_attempted"] == 0
    assert lookup["requests"][0]["adapter"] == "gws.people"
    assert lookup["requests"][1]["adapter"] == "odollo.odoo"
    assert write["phase"] == "write"
    assert write["requests"][0]["payload"]["values"]["email"] == "ada@example.test"
    assert readback["phase"] == "readback"
    assert readback["requests"][0]["simulated_readback"] is True


def test_build_sink_lookup_result_records_zero_network_matches() -> None:
    lookup_plan = build_sink_lookup_plan(
        sinks=["google_contacts"],
        spec={"full_name": "Ada Lovelace", "email": "ada@example.test"},
        dry_run=True,
        reason="matched email_domain=*",
    )
    adapter_request = build_sink_adapter_request(phase="lookup", lookup_plan=lookup_plan)

    empty = build_sink_lookup_result(adapter_request=adapter_request)
    matched = build_sink_lookup_result(
        adapter_request=adapter_request,
        matches_by_sink={
            "google_contacts": [
                {
                    "resource_id": "people/c123",
                    "confidence": 0.94,
                    "basis": ["email"],
                    "display": "Ada Lovelace",
                }
            ]
        },
    )

    assert empty["schema"] == "business-card-watchdog.sink-lookup-result.v1"
    assert empty["state"] == "no_match"
    assert empty["status"] == "not_executed"
    assert empty["network_calls_made"] == 0
    assert matched["state"] == "possible_duplicate"
    assert matched["duplicate_review_required"] is True
    assert matched["match_count"] == 1
    assert matched["results"][0]["matches"][0]["resource_id"] == "people/c123"


def test_build_sink_apply_preflight_is_zero_write_and_explicitly_gated() -> None:
    plan = build_sink_plan(
        sinks=["google_contacts"],
        spec={"full_name": "Ada Lovelace", "email": "ada@example.test"},
        dry_run=True,
        reason="matched email_domain=*",
    )

    preview = build_sink_apply_preflight(plan=plan, apply=False)
    blocked = build_sink_apply_preflight(plan=plan, apply=True)

    assert preview["schema"] == "business-card-watchdog.sink-apply-preflight.v1"
    assert preview["state"] == "preview"
    assert preview["can_apply"] is False
    assert preview["writes_attempted"] == 0
    assert preview["network_calls_made"] == 0
    assert blocked["state"] == "blocked"
    assert "not implemented" in blocked["reason"]


def test_build_sink_apply_decision_is_zero_write_and_decision_oriented() -> None:
    plan = build_sink_plan(
        sinks=["google_contacts"],
        spec={"full_name": "Ada Lovelace", "email": "ada@example.test"},
        dry_run=True,
        reason="matched email_domain=*",
    )
    preflight = build_sink_apply_preflight(plan=plan, apply=False)

    decision = build_sink_apply_decision(
        preflight=preflight,
        decision="approve",
        reviewer="operator",
        reason="pilot approved",
    )

    assert decision["schema"] == "business-card-watchdog.sink-apply-decision.v1"
    assert decision["state"] == "approved_for_apply"
    assert decision["writes_attempted"] == 0
    assert decision["network_calls_made"] == 0
    assert decision["actions"][0]["decision"] == "approve"


def test_build_sink_apply_result_blocks_live_write_after_approval() -> None:
    plan = build_sink_plan(
        sinks=["google_contacts"],
        spec={"full_name": "Ada Lovelace", "email": "ada@example.test"},
        dry_run=True,
        reason="matched email_domain=*",
    )
    preflight = build_sink_apply_preflight(plan=plan, apply=False)
    decision = build_sink_apply_decision(
        preflight=preflight,
        decision="approve",
        reviewer="operator",
    )

    result = build_sink_apply_result(preflight=preflight, decision=decision, apply=True)

    assert result["schema"] == "business-card-watchdog.sink-apply-result.v1"
    assert result["state"] == "blocked"
    assert "not implemented" in result["reason"]
    assert result["writes_attempted"] == 0
    assert result["network_calls_made"] == 0
    assert result["readback"] == []


def test_build_sink_apply_result_can_emit_mock_readback() -> None:
    plan = build_sink_plan(
        sinks=["google_contacts"],
        spec={"full_name": "Ada Lovelace", "email": "ada@example.test"},
        dry_run=True,
        reason="matched email_domain=*",
    )
    preflight = build_sink_apply_preflight(plan=plan, apply=False)
    decision = build_sink_apply_decision(preflight=preflight, decision="approve", reviewer="operator")

    result = build_sink_apply_result(preflight=preflight, decision=decision, apply=True, simulate=True)

    assert result["state"] == "mock_applied"
    assert result["simulated"] is True
    assert result["writes_attempted"] == 0
    assert result["network_calls_made"] == 0
    assert result["readback"][0]["simulated"] is True
    assert result["readback"][0]["resource_id"].startswith("mock:google_contacts:")


def test_contact_serialization_key_prefers_email_then_phone_then_name() -> None:
    assert contact_serialization_key({"phone": "+1 555 0100"}) == "phone:+1 555 0100"
    assert contact_serialization_key({"full_name": "Ada Lovelace"}).startswith("full_name:")
