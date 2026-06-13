import json
from types import SimpleNamespace

from business_card_watchdog.sink_apply_adapters import (
    execute_sink_readback_adapter,
    execute_sink_write_adapter,
    run_gws_readback,
    run_gws_write,
    run_odollo_readback,
    run_odollo_write,
)


def test_gws_write_adapter_normalizes_created_person() -> None:
    request = {
        "sink": "google_contacts",
        "phase": "write",
        "planned_action": "plan_upsert",
        "serialization_key": "email:ada@example.test",
    }

    result = execute_sink_write_adapter(
        request,
        gws_runner=lambda _: {"resourceName": "people/c123", "etag": "abc"},
    )

    assert result["status"] == "live_write_completed"
    assert result["network_calls_made"] == 1
    assert result["writes_attempted"] == 1
    assert result["write"]["resource_id"] == "people/c123"
    assert result["write"]["serialization_key"] == "email:ada@example.test"


def test_gws_readback_adapter_normalizes_person_fields() -> None:
    request = {"sink": "google_contacts", "phase": "readback"}

    result = execute_sink_readback_adapter(
        request,
        gws_runner=lambda _: {
            "resourceName": "people/c123",
            "names": [{"displayName": "Ada Lovelace"}],
            "emailAddresses": [{"value": "ada@example.test"}],
            "phoneNumbers": [{"value": "+15550101234"}],
        },
    )

    assert result["status"] == "live_readback_completed"
    assert result["writes_attempted"] == 0
    assert result["readback"]["resource_id"] == "people/c123"
    assert result["readback"]["display"] == "Ada Lovelace"
    assert result["readback"]["emails"] == ["ada@example.test"]
    assert result["readback"]["matched"] is True


def test_gws_write_runner_uses_command_vector_and_body() -> None:
    calls = []

    def command_runner(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout=json.dumps({"resourceName": "people/c123"}), stderr="")

    raw = run_gws_write(
        {
            "gws_command": ["gws", "people", "people", "createContact"],
            "request_body": {"emailAddresses": [{"value": "ada@example.test"}]},
        },
        command_runner=command_runner,
    )

    assert raw["resourceName"] == "people/c123"
    assert calls[0][0][:4] == ["gws", "people", "people", "createContact"]
    assert "--body" in calls[0][0]
    assert "--format" in calls[0][0]
    assert calls[0][1]["capture_output"] is True


def test_gws_readback_runner_uses_resource_and_params() -> None:
    calls = []

    def command_runner(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout=json.dumps({"resourceName": "people/c123"}), stderr="")

    raw = run_gws_readback(
        {
            "gws_command": ["gws", "people", "people", "get"],
            "request_body": {"resourceName": "people/c123", "personFields": "names,emailAddresses"},
        },
        command_runner=command_runner,
    )

    assert raw["resourceName"] == "people/c123"
    assert calls[0][0][:5] == ["gws", "people", "people", "get", "people/c123"]
    assert "--params" in calls[0][0]


def test_odollo_write_adapter_normalizes_partner_id() -> None:
    request = {"sink": "odoo", "phase": "write", "serialization_key": "email:ada@example.test"}

    result = execute_sink_write_adapter(request, odollo_runner=lambda _: {"id": 42})

    assert result["status"] == "live_write_completed"
    assert result["writes_attempted"] == 1
    assert result["write"]["resource_id"] == "odoo:res.partner:42"


def test_odollo_readback_adapter_normalizes_partner_row() -> None:
    request = {"sink": "odoo", "phase": "readback"}

    result = execute_sink_readback_adapter(
        request,
        odollo_runner=lambda _: [{"id": 42, "name": "Ada Lovelace", "email": "ada@example.test"}],
    )

    assert result["status"] == "live_readback_completed"
    assert result["readback"]["resource_id"] == "odoo:res.partner:42"
    assert result["readback"]["display"] == "Ada Lovelace"
    assert result["readback"]["emails"] == ["ada@example.test"]


def test_odollo_write_runner_calls_create() -> None:
    class Client:
        def __init__(self) -> None:
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            return 42

    client = Client()

    result = run_odollo_write(
        {"model": "res.partner", "values": {"name": "Ada Lovelace", "email": "ada@example.test"}},
        client=client,
    )

    assert result == 42
    assert client.calls == [
        {
            "model": "res.partner",
            "values": {"name": "Ada Lovelace", "email": "ada@example.test"},
        }
    ]


def test_odollo_readback_runner_calls_read() -> None:
    class Client:
        def __init__(self) -> None:
            self.calls = []

        def read(self, **kwargs):
            self.calls.append(kwargs)
            return [{"id": 42, "name": "Ada Lovelace"}]

    client = Client()

    rows = run_odollo_readback(
        {"model": "res.partner", "ids": [42], "fields": ["id", "name", "email"]},
        client=client,
    )

    assert rows[0]["id"] == 42
    assert client.calls == [
        {
            "model": "res.partner",
            "ids": [42],
            "fields": ["id", "name", "email"],
        }
    ]
