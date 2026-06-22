from business_card_watchdog.sinks import (
    build_odollo_tenant_readiness_packet,
    build_sink_adapter_request,
    build_sink_apply_decision,
    build_sink_apply_preflight,
    build_sink_apply_result,
    build_sink_lookup_plan,
    build_sink_lookup_pilot,
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
    readiness = check_sink_readiness("google_contacts", dry_run=True, google_contacts_profile="ecochran76")

    assert readiness.ready
    assert "dry-run" in readiness.reason
    assert readiness.details["target_account"] == "ecochran76"
    assert readiness.details["live_apply_requires_selected_target"] is True


def test_live_readiness_blocks_when_apply_disabled() -> None:
    readiness = check_sink_readiness("odoo", dry_run=False)

    assert not readiness.ready
    assert readiness.status == "blocked"
    assert "disabled" in readiness.reason


def test_live_odoo_readiness_blocks_until_local_evidence_when_apply_enabled() -> None:
    readiness = check_sink_readiness("odoo", dry_run=False, apply_enabled=True, odollo_tenant="saber")

    assert not readiness.ready
    assert readiness.status == "blocked"
    assert "Odollo" in readiness.reason


def test_live_odoo_readiness_reports_missing_config(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ODOLLO_HOME", str(tmp_path / "odollo"))

    readiness = check_sink_readiness("odoo", dry_run=False, apply_enabled=True, odollo_tenant="saber-prod")

    assert not readiness.ready
    assert readiness.status == "blocked"
    assert "user config" in readiness.reason
    assert readiness.details["config_present"] is False
    assert readiness.details["live_probe"]["network_calls_made"] == 0


def test_live_odoo_readiness_reports_local_evidence_without_call(tmp_path, monkeypatch) -> None:
    odollo_home = tmp_path / "odollo"
    tenant_home = odollo_home / "tenants" / "saber-prod"
    (tenant_home / "resources").mkdir(parents=True)
    (tenant_home / "artifacts").mkdir()
    (tenant_home / "actions.ndjson").write_text("", encoding="utf-8")
    (odollo_home / "odollo.yml").write_text("profiles: {}\n", encoding="utf-8")
    (odollo_home / "saber-prod.sqlite").write_text("", encoding="utf-8")
    monkeypatch.setenv("ODOLLO_HOME", str(odollo_home))

    readiness = check_sink_readiness("odoo", dry_run=False, apply_enabled=True, odollo_tenant="saber-prod")

    assert not readiness.ready
    assert readiness.status == "blocked"
    assert "selected-target audit" in readiness.reason
    assert "one-job pilot commands" in readiness.reason
    assert readiness.details["tenant_home_present"] is True
    assert readiness.details["state_evidence_present"] is True
    assert readiness.details["live_probe"]["status"] == "not_invoked_without_operator_approval"


def test_live_google_readiness_reports_missing_auth_evidence(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_WORKSPACE_CLI_CONFIG_DIR", str(tmp_path / "gws"))

    readiness = check_sink_readiness(
        "google_contacts",
        dry_run=False,
        apply_enabled=True,
        google_contacts_profile="codex",
    )

    assert not readiness.ready
    assert readiness.status == "blocked"
    assert "auth evidence" in readiness.reason or "gws CLI not found" in readiness.reason
    if readiness.details.get("gws_path"):
        assert readiness.details["auth_evidence_present"] is False
        assert readiness.details["config_dir"] == str(tmp_path / "gws")
        assert readiness.details["dry_run_probe"]["network_calls_made"] == 0


def test_build_sink_payloads_include_match_keys_and_readiness() -> None:
    payloads = build_sink_payloads(
        sinks=["google_contacts", "odoo"],
        spec={
            "full_name": "Ada Lovelace",
            "email": "ada@example.test",
            "contact_points": [
                {
                    "kind": "profile_url",
                    "value": "https://linkedin.com/in/ada-lovelace",
                    "label": "linkedin_url",
                }
            ],
        },
        dry_run=True,
    )

    assert [payload.sink for payload in payloads] == ["google_contacts", "odoo"]
    assert all(payload.state == "dry_run" for payload in payloads)
    assert all(payload.match_keys["email"] == "ada@example.test" for payload in payloads)
    assert payloads[0].fingerprint == payloads[1].fingerprint
    assert payloads[0].serialization_key == "email:ada@example.test"
    assert payloads[0].payload["values"]["contact_points"] == [
        {
            "kind": "profile_url",
            "value": "https://linkedin.com/in/ada-lovelace",
            "label": "linkedin_url",
        }
    ]
    assert payloads[0].payload["values"]["field_provenance"]["email"]["source"] == "flat_spec"


def test_build_sink_payloads_preserve_canonical_field_provenance() -> None:
    payloads = build_sink_payloads(
        sinks=["google_contacts"],
        spec={
            "full_name": "Ada Lovelace",
            "email": "ada@example.test",
            "_field_provenance": {
                "full_name": {
                    "source": "reviewer_correction",
                    "confidence": "observed",
                    "reason": "trimmed whitespace",
                    "provenance": [
                        {"stage": "observed", "source": "business_card_skill", "value": "A. Lovelace"},
                        {"stage": "reviewed", "source": "operator_review", "value": "Ada Lovelace"},
                    ],
                },
                "email": {
                    "source": "business_card_skill",
                    "confidence": "high",
                    "reason": "lowercased email address",
                    "provenance": [
                        {"stage": "observed", "source": "business_card_skill", "value": "ADA@EXAMPLE.TEST"},
                        {"stage": "normalized", "source": "business_card_skill", "value": "ada@example.test"},
                    ],
                },
            },
        },
        dry_run=True,
    )

    values = payloads[0].payload["values"]
    assert values["field_provenance"]["full_name"]["source"] == "reviewer_correction"
    assert values["field_provenance"]["full_name"]["provenance"][-1]["stage"] == "reviewed"
    assert values["field_provenance"]["email"]["confidence"] == "high"


def test_build_sink_plan_is_dry_run_and_action_oriented() -> None:
    plan = build_sink_plan(
        sinks=["google_contacts", "odoo"],
        spec={"full_name": "Ada Lovelace", "email": "ada@example.test"},
        dry_run=True,
        reason="matched email_domain=*",
        google_contacts_profile="ecochran76",
    )

    assert plan["schema"] == "business-card-watchdog.sink-plan.v1"
    assert plan["state"] == "dry_run"
    assert [action["sink"] for action in plan["actions"]] == ["google_contacts", "odoo"]
    assert all(action["action"] == "plan_upsert" for action in plan["actions"])
    assert plan["actions"][0]["readiness"]["details"]["target_account"] == "ecochran76"
    assert plan["actions"][0]["readiness"]["details"]["live_apply_requires_selected_target"] is True


def test_build_sink_lookup_plan_is_zero_network_and_keyed() -> None:
    plan = build_sink_lookup_plan(
        sinks=["google_contacts", "odoo"],
        spec={"full_name": "Ada Lovelace", "email": "ada@example.test", "phone": "+15550101234"},
        dry_run=True,
        reason="matched email_domain=*",
        google_contacts_profile="ecochran76",
    )

    assert plan["schema"] == "business-card-watchdog.sink-lookup-plan.v1"
    assert plan["state"] == "dry_run"
    assert plan["network_calls_made"] == 0
    assert {lookup["sink"] for lookup in plan["lookups"]} == {"google_contacts", "odoo"}
    assert all(lookup["readiness"]["status"] == "ready" for lookup in plan["lookups"])
    assert plan["lookups"][0]["match_keys"]["email"] == "ada@example.test"
    assert any(query["field"] == "email" for query in plan["lookups"][0]["queries"])
    google_lookup = next(lookup for lookup in plan["lookups"] if lookup["sink"] == "google_contacts")
    assert google_lookup["readiness"]["details"]["target_account"] == "ecochran76"
    assert google_lookup["readiness"]["details"]["live_lookup_requires_selected_target"] is True


def test_build_sink_lookup_plan_exposes_selected_odollo_tenant() -> None:
    plan = build_sink_lookup_plan(
        sinks=["odoo"],
        spec={"full_name": "Ada Lovelace", "email": "ada@example.test"},
        dry_run=True,
        reason="matched providence_context=saber",
        odollo_tenant="saber-prod",
    )

    assert plan["state"] == "dry_run"
    assert plan["network_calls_made"] == 0
    assert plan["lookups"][0]["sink"] == "odoo"
    assert plan["lookups"][0]["readiness"]["details"]["tenant"] == "saber-prod"
    assert plan["lookups"][0]["readiness"]["details"]["live_lookup_requires_selected_target"] is True


def test_odollo_tenant_readiness_reports_missing_config(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ODOLLO_HOME", str(tmp_path / "odollo"))

    packet = build_odollo_tenant_readiness_packet(tenant="saber-prod")

    assert packet["schema"] == "business-card-watchdog.odollo-tenant-readiness.v1"
    assert packet["state"] == "missing_config"
    assert packet["pilot_ready"] is False
    assert packet["network_calls_made"] == 0
    assert packet["writes_attempted"] == 0
    assert packet["blockers"][0]["category"] == "missing_config"
    assert packet["details"]["config_present"] is False
    assert packet["details"]["live_probe"]["network_calls_made"] == 0


def test_odollo_tenant_readiness_distinguishes_blocked_tenant(tmp_path, monkeypatch) -> None:
    odollo_home = tmp_path / "odollo"
    odollo_home.mkdir()
    (odollo_home / "odollo.yml").write_text("profiles: {}\n", encoding="utf-8")
    monkeypatch.setenv("ODOLLO_HOME", str(odollo_home))

    packet = build_odollo_tenant_readiness_packet(tenant="saber-prod")

    assert packet["state"] == "blocked_tenant"
    assert {blocker["category"] for blocker in packet["blockers"]} == {"blocked_tenant"}
    assert {blocker["code"] for blocker in packet["blockers"]} >= {
        "missing_tenant_home",
        "missing_tenant_state_evidence",
    }
    assert packet["details"]["config_present"] is True
    assert packet["details"]["tenant_home_present"] is False


def test_odollo_tenant_readiness_reports_pilot_ready_without_live_call(tmp_path, monkeypatch) -> None:
    odollo_home = tmp_path / "odollo"
    tenant_home = odollo_home / "tenants" / "saber-prod"
    (tenant_home / "resources").mkdir(parents=True)
    (tenant_home / "artifacts").mkdir()
    (tenant_home / "actions.ndjson").write_text("", encoding="utf-8")
    (odollo_home / "odollo.yml").write_text("profiles: {}\n", encoding="utf-8")
    (odollo_home / "saber-prod.sqlite").write_text("", encoding="utf-8")
    monkeypatch.setenv("ODOLLO_HOME", str(odollo_home))

    packet = build_odollo_tenant_readiness_packet(tenant="saber-prod")

    assert packet["state"] == "pilot_ready"
    assert packet["pilot_ready"] is True
    assert packet["blockers"] == []
    assert packet["details"]["state_evidence_present"] is True
    assert packet["details"]["live_probe"]["status"] == "not_invoked_without_operator_approval"


def test_build_sink_lookup_plan_adds_odollo_duplicate_lookup_blockers(tmp_path, monkeypatch) -> None:
    odollo_home = tmp_path / "odollo"
    tenant_home = odollo_home / "tenants" / "saber-prod"
    (tenant_home / "resources").mkdir(parents=True)
    (tenant_home / "artifacts").mkdir()
    (tenant_home / "actions.ndjson").write_text("", encoding="utf-8")
    (odollo_home / "odollo.yml").write_text("profiles: {}\n", encoding="utf-8")
    (odollo_home / "saber-prod.sqlite").write_text("", encoding="utf-8")
    monkeypatch.setenv("ODOLLO_HOME", str(odollo_home))

    plan = build_sink_lookup_plan(
        sinks=["odoo"],
        spec={"full_name": "Ada Lovelace", "email": "ada@example.test"},
        dry_run=True,
        reason="matched providence_context=saber",
        odollo_tenant="saber-prod",
    )

    lookup = plan["lookups"][0]
    assert lookup["tenant_readiness"]["state"] == "pilot_ready"
    assert lookup["duplicate_lookup_gate"]["schema"] == "business-card-watchdog.odollo-duplicate-lookup-gate.v1"
    assert lookup["duplicate_lookup_gate"]["state"] == "blocked"
    assert lookup["duplicate_lookup_gate"]["duplicate_risk"] == "unknown_until_read_only_lookup"
    assert lookup["duplicate_lookup_gate"]["blockers"][0]["category"] == "duplicate_risk"
    assert lookup["duplicate_lookup_gate"]["network_calls_made"] == 0
    assert lookup["duplicate_lookup_gate"]["writes_attempted"] == 0


def test_build_sink_plan_exposes_selected_odollo_tenant() -> None:
    plan = build_sink_plan(
        sinks=["odoo"],
        spec={"full_name": "Ada Lovelace", "email": "ada@example.test"},
        dry_run=True,
        reason="matched providence_context=soylei",
        odollo_tenant="soylei-prod",
    )

    assert plan["state"] == "dry_run"
    assert plan["actions"][0]["sink"] == "odoo"
    assert plan["actions"][0]["readiness"]["details"]["tenant"] == "soylei-prod"
    assert plan["actions"][0]["readiness"]["details"]["live_apply_requires_selected_target"] is True


def test_build_sink_adapter_request_prepares_lookup_write_and_readback_contracts() -> None:
    lookup_plan = build_sink_lookup_plan(
        sinks=["google_contacts", "odoo"],
        spec={
            "full_name": "Ada Lovelace",
            "email": "ada@example.test",
            "phone": "+15550101234",
            "organization": "Analytical Engines",
            "title": "Founder",
            "website": "https://example.test",
            "contact_points": [
                {
                    "kind": "profile_url",
                    "value": "https://linkedin.com/in/ada-lovelace",
                    "label": "linkedin_url",
                }
            ],
        },
        dry_run=True,
        reason="matched email_domain=*",
    )
    sink_plan = build_sink_plan(
        sinks=["google_contacts", "odoo"],
        spec={
            "full_name": "Ada Lovelace",
            "email": "ada@example.test",
            "phone": "+15550101234",
            "organization": "Analytical Engines",
            "title": "Founder",
            "website": "https://example.test",
            "contact_points": [
                {
                    "kind": "profile_url",
                    "value": "https://linkedin.com/in/ada-lovelace",
                    "label": "linkedin_url",
                }
            ],
        },
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
    assert lookup["requests"][0]["api"] == "people.googleapis.com"
    assert lookup["requests"][0]["gws_command"] == ["gws", "people", "people", "searchContacts"]
    assert lookup["requests"][0]["profile"]["config_key"] == "sink.google_contacts_profile"
    assert lookup["requests"][0]["request_body"]["query"] == "ada@example.test +15550101234 Ada Lovelace"
    assert "emailAddresses" in lookup["requests"][0]["request_body"]["readMask"]
    assert lookup["requests"][1]["adapter"] == "odollo.odoo"
    assert lookup["requests"][1]["tenant"]["config_key"] == "sink.odollo_tenant"
    assert lookup["requests"][1]["model"] == "res.partner"
    assert lookup["requests"][1]["domain"][0] == "|"
    assert lookup["requests"][1]["contact_point_plan"]["mode"] == "lookup_only"
    assert write["phase"] == "write"
    assert write["requests"][0]["payload"]["values"]["email"] == "ada@example.test"
    assert write["requests"][0]["method"] == "people.createContact_or_people.updateContact"
    assert write["requests"][0]["gws_command"] == ["gws", "people", "people", "createContact"]
    assert write["requests"][0]["request_body"]["organizations"][0]["name"] == "Analytical Engines"
    assert {"value": "https://example.test", "type": "work"} in write["requests"][0]["request_body"]["urls"]
    assert {
        "value": "https://linkedin.com/in/ada-lovelace",
        "type": "profile",
    } in write["requests"][0]["request_body"]["urls"]
    assert write["requests"][0]["idempotency"]["lookup_required_before_write"] is True
    assert write["requests"][1]["method"] == "create_or_write"
    assert write["requests"][1]["values"]["function"] == "Founder"
    assert write["requests"][1]["contact_point_plan"]["overwrite_canonical_slots"] is False
    assert {"kind": "website", "value": "https://example.test"} in write["requests"][1]["contact_point_plan"]["points"]
    assert {
        "kind": "profile_url",
        "value": "https://linkedin.com/in/ada-lovelace",
        "label": "linkedin_url",
    } in write["requests"][1]["contact_point_plan"]["points"]
    assert readback["phase"] == "readback"
    assert readback["requests"][0]["simulated_readback"] is True
    assert readback["requests"][0]["method"] == "people.get"
    assert readback["requests"][0]["gws_command"] == ["gws", "people", "people", "get"]
    assert readback["requests"][1]["method"] == "read"


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


def test_build_sink_lookup_pilot_requires_explicit_sink_and_approval() -> None:
    lookup_plan = build_sink_lookup_plan(
        sinks=["google_contacts"],
        spec={"full_name": "Ada Lovelace", "email": "ada@example.test"},
        dry_run=True,
        reason="matched email_domain=*",
    )
    adapter_request = build_sink_adapter_request(phase="lookup", lookup_plan=lookup_plan)

    pilot = build_sink_lookup_pilot(
        adapter_request=adapter_request,
        sink="google_contacts",
        approved_by="operator",
        matches=[
            {
                "resource_id": "people/c123",
                "confidence": 0.94,
                "basis": ["email"],
                "display": "Ada Lovelace",
            }
        ],
    )

    assert pilot["schema"] == "business-card-watchdog.sink-lookup-pilot.v1"
    assert pilot["state"] == "simulated_match"
    assert pilot["sink"] == "google_contacts"
    assert pilot["approved_by"] == "operator"
    assert pilot["read_only"] is True
    assert pilot["network_calls_made"] == 0
    assert pilot["writes_attempted"] == 0
    assert pilot["match_count"] == 1
    assert pilot["request"]["adapter"] == "gws.people"


def test_build_sink_lookup_pilot_redacts_live_execution_payloads() -> None:
    lookup_plan = build_sink_lookup_plan(
        sinks=["google_contacts"],
        spec={"full_name": "Ada Lovelace", "email": "ada@example.test"},
        dry_run=True,
        reason="matched email_domain=*",
    )
    adapter_request = build_sink_adapter_request(phase="lookup", lookup_plan=lookup_plan)

    pilot = build_sink_lookup_pilot(
        adapter_request=adapter_request,
        sink="google_contacts",
        approved_by="operator",
        simulate=False,
        redact_sensitive=True,
        execution={
            "sink": "google_contacts",
            "status": "read_only_lookup_completed",
            "network_calls_made": 1,
            "writes_attempted": 0,
            "raw": {
                "results": [
                    {
                        "person": {
                            "resourceName": "people/c123",
                            "names": [{"displayName": "Ada Lovelace"}],
                            "emailAddresses": [{"value": "ada@example.test"}],
                        }
                    }
                ]
            },
        },
        matches=[
            {
                "resource_id": "people/c123",
                "confidence": 0.94,
                "basis": ["email"],
                "display": "Ada Lovelace",
                "raw": {
                    "person": {
                        "resourceName": "people/c123",
                        "names": [{"displayName": "Ada Lovelace"}],
                        "emailAddresses": [{"value": "ada@example.test"}],
                    }
                },
            }
        ],
    )

    assert pilot["state"] == "read_only_match"
    assert pilot["execution_redacted"] is True
    assert pilot["execution"]["raw_present"] is True
    assert pilot["execution"]["raw_redacted"]["results"][0]["person"]["names"] == "[redacted]"
    assert pilot["matches"][0]["display"] == "[redacted]"
    assert "raw" not in pilot["matches"][0]
    assert pilot["matches"][0]["raw_redacted"]["person"]["emailAddresses"] == "[redacted]"


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
    assert "broad live apply is disabled" in blocked["reason"]
    assert "selected-target write/readback pilot commands" in blocked["reason"]


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
    assert "broad live apply is disabled" in result["reason"]
    assert "selected-target write/readback pilot commands" in result["reason"]
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
