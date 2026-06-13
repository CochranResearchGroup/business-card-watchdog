from business_card_watchdog.contact import (
    ENRICHMENT_MERGE_REVIEW_SCHEMA,
    REVIEWED_CONTACT_SCHEMA,
    apply_enrichment_proposals,
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


def test_enrichment_proposals_apply_only_approved_fields() -> None:
    candidate = build_contact_candidate({"full_name": "Ada Lovelace", "notes": "Card note"})

    reviewed, merge_review = apply_enrichment_proposals(
        candidate,
        reviewer="operator",
        proposals=[
            {
                "field": "notes",
                "value": "Public-web corroboration candidate: https://example.test/ada",
                "source": "public_web",
                "requires_review": True,
            },
            {
                "field": "title",
                "value": "Principal Engineer",
                "source": "public_web",
                "requires_review": True,
            },
        ],
        approved_fields=["notes"],
    )

    assert merge_review["schema"] == ENRICHMENT_MERGE_REVIEW_SCHEMA
    assert merge_review["applied"][0]["field"] == "notes"
    assert merge_review["skipped"][0]["field"] == "title"
    assert reviewed["observed"]["notes"]["source"] == "approved_enrichment"
    assert "Card note" in reviewed["flat"]["notes"]
    assert "corroboration" in reviewed["flat"]["notes"]
    assert "title" not in reviewed["flat"]
