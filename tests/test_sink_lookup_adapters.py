from business_card_watchdog.sink_lookup_adapters import execute_sink_lookup_adapter


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
