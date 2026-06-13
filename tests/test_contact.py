from business_card_watchdog.contact import (
    REVIEWED_CONTACT_SCHEMA,
    build_contact_candidate,
    contact_candidate_to_spec,
    apply_review_corrections,
)


def test_contact_candidate_preserves_observed_and_normalizes_common_fields() -> None:
    candidate = build_contact_candidate(
        {
            "full_name": " Ada   Lovelace ",
            "email": " ADA@Example.TEST ",
            "phone": "(555) 010-1234",
            "website": "www.example.test/",
        }
    )

    assert candidate["observed"]["email"]["value"] == "ADA@Example.TEST"
    assert candidate["normalized"]["full_name"]["value"] == "Ada Lovelace"
    assert candidate["normalized"]["email"]["value"] == "ada@example.test"
    assert candidate["normalized"]["phone"]["value"] == "+15550101234"
    assert candidate["normalized"]["website"]["value"] == "https://example.test"
    assert candidate["name_parts"] == {
        "display": "Ada Lovelace",
        "given": "Ada",
        "family": "Lovelace",
    }
    assert contact_candidate_to_spec(candidate)["email"] == "ada@example.test"


def test_review_corrections_create_reviewed_contact_without_losing_observed_fields() -> None:
    candidate = build_contact_candidate({"organization": "Fixture Labs"})

    reviewed = apply_review_corrections(
        candidate,
        reviewer="operator",
        field_corrections={
            "full_name": "Grace Hopper",
            "email": " GRACE@EXAMPLE.TEST ",
        },
    )

    assert reviewed["schema"] == REVIEWED_CONTACT_SCHEMA
    assert reviewed["observed"]["organization"]["value"] == "Fixture Labs"
    assert reviewed["observed"]["full_name"]["source"] == "operator_review"
    assert reviewed["normalized"]["email"]["value"] == "grace@example.test"
    assert reviewed["flat"]["full_name"] == "Grace Hopper"
