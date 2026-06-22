import json
from pathlib import Path

from business_card_watchdog.config import AppConfig, EnrichmentConfig, EnrichmentProviderConfig, PrefilterConfig
from business_card_watchdog.contact import build_contact_candidate
from business_card_watchdog.enrichment import (
    build_enrichment_request,
    build_paid_api_provider_handoff,
    build_paid_api_provider_request,
    build_public_web_queries,
    build_public_web_result_artifact,
    build_public_web_search_handoff,
    build_public_web_search_request,
    check_enrichment_readiness,
    score_paid_api_provider_results,
    score_public_web_results,
)
from business_card_watchdog.orchestrator import BatchOrchestrator
from business_card_watchdog.service import BusinessCardService

from synthetic_fixtures import SyntheticSkillAdapter, latest_jobs_by_id, read_jsonl, write_synthetic_image


def test_enrichment_defaults_to_no_requested_work(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml")

    payload = BusinessCardService(config).enrichment_readiness()

    assert payload["enabled"] is False
    assert payload["checks"][0]["status"] == "ready"
    assert payload["checks"][0]["reason"] == "enrichment not requested"


def test_public_web_enrichment_requires_enabled_config(tmp_path: Path) -> None:
    disabled = AppConfig(config_path=tmp_path / "config.toml")
    enabled = AppConfig(
        config_path=tmp_path / "config.toml",
        enrichment=EnrichmentConfig(enabled=True),
    )

    assert check_enrichment_readiness(disabled, mode="public_web")[0].status == "blocked"
    public_web = check_enrichment_readiness(enabled, mode="public_web")[0]
    assert public_web.status == "ready"
    assert public_web.cost_class == "operator_search"


def test_paid_api_enrichment_requires_config_flag_operator_flag_and_key_name(tmp_path: Path) -> None:
    keys_path = tmp_path / "API-keys.env"
    base = EnrichmentConfig(
        enabled=True,
        allow_paid_api=True,
        api_keys_env=keys_path,
        apollo=EnrichmentProviderConfig(enabled=True, api_key_env="APOLLO_API_KEY"),
    )
    config = AppConfig(config_path=tmp_path / "config.toml", enrichment=base)

    blocked_without_operator_flag = check_enrichment_readiness(config, mode="api")[0]
    assert blocked_without_operator_flag.status == "blocked"
    assert "explicit operator request" in blocked_without_operator_flag.reason

    missing_key = check_enrichment_readiness(config, mode="api", allow_paid_enrichment=True)[0]
    assert missing_key.status == "blocked"
    assert missing_key.missing_key == "APOLLO_API_KEY"

    keys_path.write_text("APOLLO_API_KEY=fixture-value-redacted\n", encoding="utf-8")
    ready = check_enrichment_readiness(config, mode="api", allow_paid_enrichment=True)[0]
    assert ready.status == "ready"
    assert ready.missing_key is None
    assert "secret" not in ready.to_dict()["reason"]


def test_public_web_request_builds_queries_from_contact_candidate() -> None:
    request = build_enrichment_request(
        {
            "schema": "business-card-watchdog.contact-candidate.v1",
            "normalized": {
                "full_name": {"value": "Ada Lovelace"},
                "organization": {"value": "Example Labs"},
                "email": {"value": "ada@example.test"},
            },
        },
        mode="public_web",
    )

    assert request["schema"] == "business-card-watchdog.enrichment-request.v1"
    assert request["queries"][0]["query"] == '"ada@example.test"'
    assert request["cost_gate"]["paid_api_requested"] is False


def test_public_web_search_request_is_zero_network_and_operator_scoped(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        enrichment=EnrichmentConfig(enabled=True, max_public_web_queries_per_contact=2),
    )
    readiness = [
        check.to_dict()
        for check in check_enrichment_readiness(config, mode="public_web")
    ]

    request = build_public_web_search_request(
        config,
        {
            "schema": "business-card-watchdog.contact-candidate.v1",
            "normalized": {
                "full_name": {"value": "Ada Lovelace"},
                "organization": {"value": "Example Labs"},
                "email": {"value": "ada@example.test"},
                "website": {"value": "https://example.test/team"},
            },
        },
        mode="public_web",
        requested_by="tester",
        readiness=readiness,
    )

    assert request["schema"] == "business-card-watchdog.enrichment-public-web-request.v1"
    assert request["status"] == "prepared"
    assert request["cost_class"] == "operator_search"
    assert request["network_calls_made"] == 0
    assert request["search_calls_attempted"] == 0
    assert request["max_queries"] == 2
    assert len(request["queries"]) == 2
    assert request["queries"][0]["search_url"].startswith("https://www.google.com/search?q=")
    assert "paid API" in request["instructions"][2]


def test_public_web_queries_include_odollo_derived_phone_forms() -> None:
    queries = build_public_web_queries(
        {
            "full_name": "Ada Lovelace",
            "organization": "Example Labs",
            "phone": "(555) 010-1234",
        },
        max_queries=6,
    )

    assert queries[0] == {"query": '"555-010-1234"', "purpose": "exact_phone", "required": True}
    assert {"query": '"5550101234"', "purpose": "exact_phone", "required": True} in queries
    assert {
        "query": '"555-010-1234" "Ada Lovelace"',
        "purpose": "phone_with_context",
        "required": False,
    } in queries


def test_public_web_scoring_uses_phone_hits_and_directory_penalty_context() -> None:
    result = score_public_web_results(
        build_contact_candidate(
            {
                "full_name": "Ada Lovelace",
                "organization": "Example Labs",
                "phone": "(555) 010-1234",
            }
        ),
        results=[
            {
                "title": "Ada Lovelace - Example Labs",
                "url": "https://example.test/team/ada",
                "snippet": "Call (555) 010-1234 for Example Labs.",
            },
            {
                "title": "Directory row",
                "url": "https://yellowpages.com/example-labs",
                "snippet": "Call 5550101234.",
            },
        ],
    )

    assert result["reuse_note"] == "adapted_from_odollo_enrichment_patterns"
    assert result["results"][0]["phone_hits"]
    assert "phone" in result["results"][0]["signals"]
    assert "non_directory_source" in result["results"][0]["signals"]
    assert result["results"][0]["domain"] == "example.test"


def test_public_web_result_artifact_scores_explicit_operator_results(tmp_path: Path) -> None:
    candidate = build_contact_candidate(
        {
            "full_name": "Ada Lovelace",
            "organization": "Example Labs",
            "email": "ada@example.test",
        }
    )
    public_web_request = {
        "schema": "business-card-watchdog.enrichment-public-web-request.v1",
        "mode": "public_web",
        "status": "prepared",
        "max_queries": 1,
        "queries": [{"query": '"ada@example.test"'}],
    }

    result = build_public_web_result_artifact(
        candidate,
        public_web_request=public_web_request,
        searched_by="tester",
        results=[
            {
                "title": "Ada Lovelace - Example Labs",
                "url": "https://example.test/team/ada",
                "snippet": "Contact Ada at ada@example.test",
            }
        ],
    )

    assert result["schema"] == "business-card-watchdog.enrichment-public-web-result.v1"
    assert result["reuse_note"] == "adapted_from_odollo_enrichment_patterns"
    assert result["result_schema"] == "business-card-watchdog.enrichment-result.v1"
    assert result["searched_by"] == "tester"
    assert result["source_query_count"] == 1
    assert result["max_results"] == 1
    assert result["submitted_result_count"] == 1
    assert result["network_calls_made"] == 0
    assert result["search_calls_attempted"] == 0
    assert result["results"][0]["score"] >= 75
    assert result["merge_proposals"][0]["field"] == "notes"


def test_public_web_search_handoff_is_zero_network_and_import_scoped() -> None:
    request = {
        "schema": "business-card-watchdog.enrichment-public-web-request.v1",
        "mode": "public_web",
        "status": "prepared",
        "max_queries": 2,
        "queries": [
            {
                "kind": "person_org",
                "query": '"Ada Lovelace" "Example Labs"',
                "search_url": "https://www.google.com/search?q=%22Ada+Lovelace%22+%22Example+Labs%22",
            }
        ],
    }

    handoff = build_public_web_search_handoff(request, run_id="run-1", job_id="job-1")

    assert handoff["schema"] == "business-card-watchdog.enrichment-public-web-search-handoff.v1"
    assert handoff["source_request_schema"] == request["schema"]
    assert handoff["source_request_status"] == "prepared"
    assert handoff["cost_class"] == "operator_search"
    assert handoff["network_calls_made"] == 0
    assert handoff["search_calls_attempted"] == 0
    assert handoff["query_count"] == 1
    assert handoff["max_queries"] == 2
    assert handoff["result_import"]["mcp_tool"] == "business_card_watchdog_public_web_enrichment_results"
    assert "public-web-results job-1 --run-id run-1" in handoff["result_import"]["cli"]


def test_paid_api_provider_request_is_zero_network_and_secret_free(tmp_path: Path) -> None:
    keys_path = tmp_path / "API-keys.env"
    keys_path.write_text("APOLLO_API_KEY=fixture-value-redacted\n", encoding="utf-8")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        enrichment=EnrichmentConfig(
            enabled=True,
            allow_paid_api=True,
            api_keys_env=keys_path,
            apollo=EnrichmentProviderConfig(enabled=True),
        ),
    )
    readiness = [
        check.to_dict()
        for check in check_enrichment_readiness(config, mode="api", allow_paid_enrichment=True)
    ]

    request = build_paid_api_provider_request(
        config,
        {
            "schema": "business-card-watchdog.contact-candidate.v1",
            "normalized": {
                "full_name": {"value": "Ada Lovelace"},
                "organization": {"value": "Example Labs"},
                "email": {"value": "ada@example.test"},
                "website": {"value": "https://example.test/team"},
            },
        },
        mode="api",
        requested_by="tester",
        allow_paid_enrichment=True,
        readiness=readiness,
    )

    assert request["schema"] == "business-card-watchdog.enrichment-provider-request.v1"
    assert request["status"] == "prepared"
    assert request["network_calls_made"] == 0
    assert request["paid_api_calls_attempted"] == 0
    assert request["max_results"] == 5
    assert request["api_key_env"] == "APOLLO_API_KEY"
    assert request["api_key_available"] is True
    assert request["request_fields"]["domain"] == "example.test"
    assert "secret" not in str(request)


def test_people_data_labs_provider_contract_is_zero_call_and_secret_free(tmp_path: Path) -> None:
    keys_path = tmp_path / "API-keys.env"
    keys_path.write_text("PDL_API_KEY=fixture-value-redacted\n", encoding="utf-8")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        enrichment=EnrichmentConfig(
            enabled=True,
            allow_paid_api=True,
            api_keys_env=keys_path,
            people_data_labs=EnrichmentProviderConfig(
                enabled=True,
                api_key_env="PDL_API_KEY",
                base_url="https://api.peopledatalabs.com/v5/person/enrich",
            ),
        ),
    )
    readiness = [
        check.to_dict()
        for check in check_enrichment_readiness(
            config,
            mode="api",
            allow_paid_enrichment=True,
            provider="people_data_labs",
        )
    ]

    request = build_paid_api_provider_request(
        config,
        build_contact_candidate(
            {
                "full_name": "Ada Lovelace",
                "organization": "Example Labs",
                "email": "ada@example.test",
                "phone": "555-010-1234",
                "website": "https://example.test/team",
            }
        ),
        mode="api",
        requested_by="tester",
        allow_paid_enrichment=True,
        readiness=readiness,
        provider="people_data_labs",
    )
    result = score_paid_api_provider_results(
        build_contact_candidate(
            {
                "full_name": "Ada Lovelace",
                "organization": "Example Labs",
                "email": "ada@example.test",
            }
        ),
        provider="people_data_labs",
        results=[
            {
                "status": 200,
                "likelihood": 10,
                "data": {
                    "full_name": "Ada Lovelace",
                    "work_email": "ada@example.test",
                    "job_title": "Principal",
                    "job_company_name": "Example Labs",
                    "job_company_website": "example.test",
                },
            }
        ],
    )

    assert readiness[0]["status"] == "ready"
    assert readiness[0]["provider"] == "people_data_labs"
    assert request["schema"] == "business-card-watchdog.enrichment-provider-request.v1"
    assert request["provider"] == "people_data_labs"
    assert request["operation"] == "person_enrichment"
    assert request["api_key_env"] == "PDL_API_KEY"
    assert request["request_fields"]["company"] == "Example Labs"
    assert request["request_fields"]["phone"] == "+15550101234"
    assert request["network_calls_made"] == 0
    assert request["paid_api_calls_attempted"] == 0
    assert "fixture-value-redacted" not in json.dumps(request)
    assert result["provider"] == "people_data_labs"
    assert result["results"][0]["title"] == "Principal"
    assert result["results"][0]["organization"] == "Example Labs"
    assert result["paid_api_calls_attempted"] == 0
    assert any(proposal["field"] == "title" for proposal in result["merge_proposals"])


def test_paid_api_provider_handoff_is_explicit_and_secret_free() -> None:
    provider_request = {
        "schema": "business-card-watchdog.enrichment-provider-request.v1",
        "provider": "apollo",
        "mode": "api",
        "status": "prepared",
        "operation": "person_company_lookup",
        "allow_paid_enrichment": True,
        "max_results": 2,
        "api_key_env": "APOLLO_API_KEY",
        "api_key_available": True,
        "base_url": "https://api.apollo.io",
        "request_fields": {"email": "ada@example.test"},
    }

    handoff = build_paid_api_provider_handoff(provider_request, run_id="run-1", job_id="job-1")

    assert handoff["schema"] == "business-card-watchdog.enrichment-provider-handoff.v1"
    assert handoff["cost_class"] == "paid_api"
    assert handoff["allow_paid_enrichment"] is True
    assert handoff["network_calls_made"] == 0
    assert handoff["paid_api_calls_attempted"] == 0
    assert handoff["max_results"] == 2
    assert handoff["api_key_env"] == "APOLLO_API_KEY"
    assert handoff["result_import"]["mcp_tool"] == "business_card_watchdog_provider_enrichment_results"
    assert "provider-results job-1 --run-id run-1" in handoff["result_import"]["cli"]
    assert "secret" not in json.dumps(handoff)


def test_paid_api_provider_results_are_reviewable_without_call() -> None:
    result = score_paid_api_provider_results(
        build_contact_candidate(
            {
                "full_name": "Ada Lovelace",
                "organization": "Example Labs",
                "email": "ada@example.test",
            }
        ),
        provider="apollo",
        results=[
            {
                "person": {
                    "name": "Ada Lovelace",
                    "email": "ada@example.test",
                    "title": "Principal",
                },
                "organization": {
                    "name": "Example Labs",
                    "website_url": "https://example.test",
                },
            }
        ],
    )

    assert result["schema"] == "business-card-watchdog.enrichment-provider-result.v1"
    assert result["reuse_note"] == "adapted_from_odollo_enrichment_patterns"
    assert result["result_schema"] == "business-card-watchdog.enrichment-result.v1"
    assert result["provider"] == "apollo"
    assert result["network_calls_made"] == 0
    assert result["paid_api_calls_attempted"] == 0
    assert result["max_results"] == 1
    assert result["submitted_result_count"] == 1
    assert result["results"][0]["score"] >= 80
    assert any(proposal["field"] == "title" for proposal in result["merge_proposals"])


def test_apollo_provider_result_extraction_accepts_contact_wrappers() -> None:
    result = score_paid_api_provider_results(
        build_contact_candidate({"full_name": "Ada Lovelace", "email": "ada@example.test"}),
        provider="apollo",
        results=[
            {
                "contact": {
                    "id": "apollo-contact-1",
                    "name": "Ada Lovelace",
                    "email": "ada@example.test",
                    "title": "Principal",
                },
                "account": {"name": "Example Labs", "domain": "example.test"},
            }
        ],
    )

    assert result["network_calls_made"] == 0
    assert result["paid_api_calls_attempted"] == 0
    assert result["results"][0]["full_name"] == "Ada Lovelace"
    assert result["results"][0]["email"] == "ada@example.test"
    assert result["results"][0]["organization"] == "Example Labs"


def test_service_request_enrichment_writes_request_and_fixture_result(tmp_path: Path, monkeypatch) -> None:
    source_dir = tmp_path / "synthetic-cards"
    write_synthetic_image(source_dir / "card.png")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        prefilter=PrefilterConfig(process_uncertain=True),
        enrichment=EnrichmentConfig(enabled=True),
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(
        orchestrator,
        "adapter",
        SyntheticSkillAdapter(
            specs_by_stem={
                "card": {
                    "full_name": "Ada Lovelace",
                    "organization": "Example Labs",
                    "email": "ada@example.test",
                }
            }
        ),
    )
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)
    job = next(iter(latest_jobs_by_id(run_dir / "jobs.jsonl").values()))

    payload = BusinessCardService(config).request_enrichment(
        job_id=job["job_id"],
        run_id=run_dir.name,
        mode="public_web",
        requested_by="tester",
        public_web_results=[
            {
                "title": "Ada Lovelace - Example Labs",
                "url": "https://example.test/team/ada",
                "snippet": "Contact Ada at ada@example.test",
            }
        ],
    )
    artifacts = read_jsonl(run_dir / "artifacts.jsonl")
    result_path = Path(payload["result_path"])

    assert payload["status"] == "ok"
    assert payload["public_web_request"]["schema"] == "business-card-watchdog.enrichment-public-web-request.v1"
    assert payload["public_web_request"]["network_calls_made"] == 0
    assert payload["result"]["network_calls_made"] == 0
    assert payload["result"]["results"][0]["score"] >= 75
    assert result_path.exists()
    assert any(artifact["kind"] == "enrichment_request" for artifact in artifacts)
    assert any(artifact["kind"] == "enrichment_public_web_request" for artifact in artifacts)
    assert any(artifact["kind"] == "enrichment_result" for artifact in artifacts)


def test_service_records_public_web_results_after_request(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        enrichment=EnrichmentConfig(enabled=True),
    )
    run_id = "run-public-web-results"
    job_id = "job-public-web-results"
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    from business_card_watchdog.ledger import RunLedger
    from business_card_watchdog.models import CardJob

    ledger = RunLedger(config.runs_dir / run_id)
    ledger.initialize(source="/tmp/cards", dry_run=True)
    job = CardJob(image_path="/tmp/cards/card.png", job_id=job_id)
    job.transition_to("processing")
    job.artifact_dir = str(artifact_dir)
    job.transition_to("needs_review")
    ledger.record_job(job)
    candidate = build_contact_candidate(
        {
            "full_name": "Ada Lovelace",
            "organization": "Example Labs",
            "email": "ada@example.test",
        }
    )
    (artifact_dir / "contact_candidate.json").write_text(json.dumps(candidate, indent=2), encoding="utf-8")
    service = BusinessCardService(config)
    service.request_enrichment(job_id=job_id, run_id=run_id, mode="public_web", requested_by="tester")

    payload = service.record_public_web_enrichment_results(
        job_id=job_id,
        run_id=run_id,
        searched_by="search-agent",
        results=[
            {
                "title": "Ada Lovelace - Example Labs",
                "url": "https://example.test/team/ada",
                "snippet": "Contact Ada at ada@example.test",
            }
        ],
    )
    artifacts = read_jsonl(config.runs_dir / run_id / "artifacts.jsonl")
    events = read_jsonl(config.runs_dir / run_id / "events.jsonl")

    assert payload["public_web_result"]["schema"] == "business-card-watchdog.enrichment-public-web-result.v1"
    assert payload["public_web_result"]["searched_by"] == "search-agent"
    assert payload["public_web_result"]["network_calls_made"] == 0
    assert payload["result"]["schema"] == "business-card-watchdog.enrichment-result.v1"
    assert payload["result"]["merge_proposals"][0]["field"] == "notes"
    assert any(artifact["kind"] == "enrichment_public_web_result" for artifact in artifacts)
    assert any(artifact["kind"] == "enrichment_result" for artifact in artifacts)
    assert any(event["event_type"] == "enrichment_public_web_results_recorded" for event in events)


def test_service_creates_public_web_search_handoff_after_request(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        enrichment=EnrichmentConfig(enabled=True, max_public_web_queries_per_contact=2),
    )
    run_id, job_id = _record_candidate(config)
    service = BusinessCardService(config)
    service.request_enrichment(job_id=job_id, run_id=run_id, mode="public_web", requested_by="tester")

    payload = service.build_public_web_enrichment_handoff(job_id=job_id, run_id=run_id)
    artifacts = read_jsonl(config.runs_dir / run_id / "artifacts.jsonl")
    events = read_jsonl(config.runs_dir / run_id / "events.jsonl")

    assert payload["status"] == "ok"
    assert Path(payload["handoff_path"]).exists()
    assert payload["handoff"]["schema"] == "business-card-watchdog.enrichment-public-web-search-handoff.v1"
    assert payload["handoff"]["network_calls_made"] == 0
    assert payload["handoff"]["search_calls_attempted"] == 0
    assert payload["handoff"]["max_queries"] == 2
    assert any(artifact["kind"] == "enrichment_public_web_search_handoff" for artifact in artifacts)
    assert any(event["event_type"] == "enrichment_public_web_search_handoff_created" for event in events)


def test_service_public_web_result_import_enforces_request_limit(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        enrichment=EnrichmentConfig(enabled=True, max_public_web_queries_per_contact=1),
    )
    run_id, job_id = _record_candidate(config)
    service = BusinessCardService(config)
    service.request_enrichment(job_id=job_id, run_id=run_id, mode="public_web", requested_by="tester")

    try:
        service.record_public_web_enrichment_results(
            job_id=job_id,
            run_id=run_id,
            searched_by="search-agent",
            results=[
                {"title": "one", "url": "https://one.example.test", "snippet": "one"},
                {"title": "two", "url": "https://two.example.test", "snippet": "two"},
            ],
        )
    except ValueError as exc:
        assert "exceeds request limit" in str(exc)
    else:
        raise AssertionError("expected oversized public-web result import to fail")


def test_service_request_api_enrichment_writes_provider_request_without_call(tmp_path: Path) -> None:
    keys_path = tmp_path / "API-keys.env"
    keys_path.write_text("APOLLO_API_KEY=fixture-value-redacted\n", encoding="utf-8")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        enrichment=EnrichmentConfig(
            enabled=True,
            allow_paid_api=True,
            api_keys_env=keys_path,
            apollo=EnrichmentProviderConfig(enabled=True),
        ),
    )
    service = BusinessCardService(config)
    run_id, job_id = _record_candidate(config)

    payload = service.request_enrichment(
        job_id=job_id,
        run_id=run_id,
        mode="api",
        requested_by="tester",
        allow_paid_enrichment=True,
        provider_results=[
            {
                "person": {
                    "name": "Ada Lovelace",
                    "email": "ada@example.test",
                    "title": "Principal",
                },
                "organization": {"name": "Example Labs"},
            }
        ],
    )
    artifacts = read_jsonl(config.runs_dir / run_id / "artifacts.jsonl")

    assert payload["status"] == "ok"
    assert payload["result"]["schema"] == "business-card-watchdog.enrichment-provider-result.v1"
    assert payload["provider_request"]["status"] == "prepared"
    assert payload["provider_result"]["paid_api_calls_attempted"] == 0
    assert payload["provider_request"]["max_results"] == 5
    assert payload["provider_result"]["max_results"] == 5
    assert payload["provider_result"]["submitted_result_count"] == 1
    assert payload["provider_request"]["network_calls_made"] == 0
    assert payload["provider_request"]["paid_api_calls_attempted"] == 0
    assert "secret" not in Path(payload["provider_request_path"]).read_text(encoding="utf-8")
    assert any(artifact["kind"] == "enrichment_provider_request" for artifact in artifacts)
    assert any(artifact["kind"] == "enrichment_provider_result" for artifact in artifacts)
    assert any(artifact["kind"] == "enrichment_result" for artifact in artifacts)


def test_service_creates_provider_handoff_and_records_results_after_request(tmp_path: Path) -> None:
    keys_path = tmp_path / "API-keys.env"
    keys_path.write_text("APOLLO_API_KEY=fixture-value-redacted\n", encoding="utf-8")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        enrichment=EnrichmentConfig(
            enabled=True,
            allow_paid_api=True,
            api_keys_env=keys_path,
            max_paid_provider_results_per_contact=2,
            apollo=EnrichmentProviderConfig(enabled=True),
        ),
    )
    service = BusinessCardService(config)
    run_id, job_id = _record_candidate(config)
    service.request_enrichment(
        job_id=job_id,
        run_id=run_id,
        mode="api",
        requested_by="tester",
        allow_paid_enrichment=True,
    )

    handoff = service.build_provider_enrichment_handoff(job_id=job_id, run_id=run_id)
    payload = service.record_provider_enrichment_results(
        job_id=job_id,
        run_id=run_id,
        provider="apollo",
        submitted_by="api-agent",
        results=[
            {
                "person": {
                    "name": "Ada Lovelace",
                    "email": "ada@example.test",
                    "title": "Principal",
                },
                "organization": {"name": "Example Labs"},
            }
        ],
    )
    artifacts = read_jsonl(config.runs_dir / run_id / "artifacts.jsonl")
    events = read_jsonl(config.runs_dir / run_id / "events.jsonl")

    assert handoff["handoff"]["schema"] == "business-card-watchdog.enrichment-provider-handoff.v1"
    assert handoff["handoff"]["paid_api_calls_attempted"] == 0
    assert handoff["handoff"]["max_results"] == 2
    assert "secret" not in Path(handoff["handoff_path"]).read_text(encoding="utf-8")
    assert payload["provider_result"]["schema"] == "business-card-watchdog.enrichment-provider-result.v1"
    assert payload["provider_result"]["submitted_by"] == "api-agent"
    assert payload["provider_result"]["paid_api_calls_attempted"] == 0
    assert payload["provider_result"]["max_results"] == 2
    assert payload["result"]["schema"] == "business-card-watchdog.enrichment-result.v1"
    assert any(artifact["kind"] == "enrichment_provider_handoff" for artifact in artifacts)
    assert any(artifact["kind"] == "enrichment_provider_result" for artifact in artifacts)
    assert any(event["event_type"] == "enrichment_provider_handoff_created" for event in events)
    assert any(event["event_type"] == "enrichment_provider_results_recorded" for event in events)


def test_service_paid_provider_result_import_enforces_request_limit(tmp_path: Path) -> None:
    keys_path = tmp_path / "API-keys.env"
    keys_path.write_text("APOLLO_API_KEY=fixture-value-redacted\n", encoding="utf-8")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        enrichment=EnrichmentConfig(
            enabled=True,
            allow_paid_api=True,
            api_keys_env=keys_path,
            max_paid_provider_results_per_contact=1,
            apollo=EnrichmentProviderConfig(enabled=True),
        ),
    )
    service = BusinessCardService(config)
    run_id, job_id = _record_candidate(config)

    try:
        service.request_enrichment(
            job_id=job_id,
            run_id=run_id,
            mode="api",
            requested_by="tester",
            allow_paid_enrichment=True,
            provider_results=[
                {"person": {"name": "Ada Lovelace", "email": "ada@example.test"}},
                {"person": {"name": "Ada Byron", "email": "ada.byron@example.test"}},
            ],
        )
    except ValueError as exc:
        assert "paid provider result import exceeds request limit" in str(exc)
    else:
        raise AssertionError("expected oversized paid provider result import to fail")

    artifacts = read_jsonl(config.runs_dir / run_id / "artifacts.jsonl")
    assert any(artifact["kind"] == "enrichment_provider_request" for artifact in artifacts)
    assert not any(artifact["kind"] == "enrichment_provider_result" for artifact in artifacts)


def _record_candidate(config: AppConfig) -> tuple[str, str]:
    from business_card_watchdog.ledger import RunLedger
    from business_card_watchdog.models import CardJob

    run_id = "run-enrichment-api"
    ledger = RunLedger(config.runs_dir / run_id)
    ledger.initialize(source="/tmp/cards", dry_run=True)
    job = CardJob(image_path="/tmp/cards/card.png", job_id="job-enrichment-api")
    artifact_dir = ledger.run_dir / "artifacts" / job.job_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    candidate = {
        "schema": "business-card-watchdog.contact-candidate.v1",
        "normalized": {
            "full_name": {"value": "Ada Lovelace"},
            "organization": {"value": "Example Labs"},
            "email": {"value": "ada@example.test"},
            "website": {"value": "https://example.test/team"},
        },
    }
    candidate_path = artifact_dir / "contact_candidate.json"
    candidate_path.write_text(json.dumps(candidate) + "\n", encoding="utf-8")
    job.artifact_dir = str(artifact_dir)
    job.transition_to("processing")
    job.transition_to("needs_review")
    ledger.set_job_count(1)
    ledger.record_job(job)
    ledger.record_artifact(job_id=job.job_id, kind="contact_candidate", path=candidate_path)
    return run_id, job.job_id
