import json
from types import SimpleNamespace

from business_card_watchdog.sink_lookup_adapters import execute_sink_lookup_adapter, run_gws_lookup, run_odollo_lookup


def test_gws_lookup_adapter_normalizes_people_results() -> None:
    request = {
        "sink": "google_contacts",
        "phase": "lookup",
        "gws_command": ["gws", "people", "people", "searchContacts"],
        "request_body": {"query": "ada@example.test"},
    }

    result = execute_sink_lookup_adapter(
        request,
        gws_runner=lambda _: {
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
    )

    assert result["status"] == "read_only_lookup_completed"
    assert result["network_calls_made"] == 1
    assert result["writes_attempted"] == 0
    assert result["matches"][0]["resource_id"] == "people/c123"
    assert result["matches"][0]["basis"] == ["email", "full_name"]


def test_gws_lookup_runner_uses_command_vector_and_params() -> None:
    calls = []

    def command_runner(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "results": [
                        {
                            "person": {
                                "resourceName": "people/c123",
                                "emailAddresses": [{"value": "ada@example.test"}],
                            }
                        }
                    ]
                }
            ),
            stderr="",
        )

    raw = run_gws_lookup(
        {
            "gws_command": ["gws", "people", "people", "searchContacts"],
            "request_body": {"query": "ada@example.test", "readMask": "names,emailAddresses"},
        },
        command_runner=command_runner,
    )

    assert raw["results"][0]["person"]["resourceName"] == "people/c123"
    assert calls[0][0][:4] == ["gws", "people", "people", "searchContacts"]
    assert "--params" in calls[0][0]
    assert "--format" in calls[0][0]
    assert calls[0][1]["capture_output"] is True


def test_odollo_lookup_adapter_normalizes_partner_rows() -> None:
    request = {
        "sink": "odoo",
        "phase": "lookup",
        "model": "res.partner",
        "domain": [["email", "=", "ada@example.test"]],
        "fields": ["id", "name", "email"],
        "limit": 10,
    }

    result = execute_sink_lookup_adapter(
        request,
        odollo_runner=lambda _: [
            {"id": 42, "name": "Ada Lovelace", "email": "ada@example.test"}
        ],
    )

    assert result["status"] == "read_only_lookup_completed"
    assert result["network_calls_made"] == 1
    assert result["writes_attempted"] == 0
    assert result["matches"][0]["resource_id"] == "odoo:res.partner:42"
    assert result["matches"][0]["basis"] == ["email", "full_name"]


def test_odollo_lookup_runner_calls_search_read_only() -> None:
    class Client:
        def __init__(self) -> None:
            self.calls = []

        def search_read(self, **kwargs):
            self.calls.append(kwargs)
            return [{"id": 42, "name": "Ada Lovelace", "email": "ada@example.test"}]

    client = Client()

    rows = run_odollo_lookup(
        {
            "model": "res.partner",
            "domain": [["email", "=", "ada@example.test"]],
            "fields": ["id", "name", "email"],
            "limit": 10,
        },
        client=client,
    )

    assert rows[0]["id"] == 42
    assert client.calls == [
        {
            "model": "res.partner",
            "domain": [["email", "=", "ada@example.test"]],
            "fields": ["id", "name", "email"],
            "limit": 10,
        }
    ]
