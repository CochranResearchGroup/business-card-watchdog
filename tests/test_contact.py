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
    assert candidate["normalized"]["email"]["confidence"] == "high"
    assert candidate["normalized"]["phone"]["value"] == "+15550101234"
    assert candidate["normalized"]["phone"]["reason"] == "normalized to E.164"
    assert candidate["normalized"]["website"]["value"] == "https://example.test"
    assert candidate["contact_points"] == [
        {
            "kind": "email",
            "value": "ada@example.test",
            "source": "business_card_skill",
            "raw": "ADA@Example.TEST",
            "confidence": "high",
            "reason": "lowercased email address",
        },
        {
            "kind": "phone",
            "value": "+15550101234",
            "source": "business_card_skill",
            "raw": "(555) 010-1234",
            "confidence": "high",
            "reason": "normalized to E.164",
        },
        {
            "kind": "website",
            "value": "https://example.test",
            "source": "business_card_skill",
            "raw": "www.example.test/",
            "confidence": "high",
            "reason": "normalized website host and scheme",
        },
    ]
    assert candidate["name_parts"] == {
        "display": "Ada Lovelace",
        "given": "Ada",
        "family": "Lovelace",
    }
    assert contact_candidate_to_spec(candidate)["email"] == "ada@example.test"


def test_contact_candidate_marks_non_default_country_phone_for_review() -> None:
    candidate = build_contact_candidate(
        {
            "phone": "020 7946 0958",
        },
        default_country="GB",
    )

    assert candidate["normalization"]["default_country"] == "GB"
    assert candidate["normalized"]["phone"]["e164"] is None
    assert candidate["normalized"]["phone"]["confidence"] == "review"
    assert candidate["contact_points"][0]["kind"] == "phone"
    assert candidate["contact_points"][0]["reason"] == "phone could not be normalized to E.164"


def test_review_corrections_create_reviewed_contact_without_losing_observed_fields() -> None:
    candidate = build_contact_candidate(
        {
            "organization": "Fixture Labs",
            "linkedin": "linkedin.com/in/grace-hopper",
        }
    )

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
    assert reviewed["contact_points"][0]["source"] == "operator_review"
    assert reviewed["extras"]["linkedin"] == "linkedin.com/in/grace-hopper"
    assert {
        "kind": "profile_url",
        "value": "https://linkedin.com/in/grace-hopper",
        "source": "business_card_skill",
        "raw": "linkedin.com/in/grace-hopper",
        "confidence": "high",
        "reason": "normalized profile URL",
        "label": "linkedin",
    } in reviewed["contact_points"]
    assert reviewed["flat"]["full_name"] == "Grace Hopper"


def test_contact_candidate_adds_profile_url_contact_points_from_extras() -> None:
    candidate = build_contact_candidate(
        {
            "full_name": "Ada Lovelace",
            "linkedin_url": "https://www.linkedin.com/in/ada-lovelace/",
            "social_profile": ["github.com/ada"],
        }
    )

    assert candidate["extras"]["linkedin_url"] == "https://www.linkedin.com/in/ada-lovelace/"
    assert {
        "kind": "profile_url",
        "value": "https://linkedin.com/in/ada-lovelace",
        "source": "business_card_skill",
        "raw": "https://www.linkedin.com/in/ada-lovelace/",
        "confidence": "high",
        "reason": "normalized profile URL",
        "label": "linkedin_url",
    } in candidate["contact_points"]
    assert {
        "kind": "profile_url",
        "value": "https://github.com/ada",
        "source": "business_card_skill",
        "raw": "github.com/ada",
        "confidence": "high",
        "reason": "normalized profile URL",
        "label": "social_profile",
    } in candidate["contact_points"]
    assert "linkedin_url" not in candidate["flat"]


def test_enrichment_proposals_apply_only_approved_fields() -> None:
    candidate = build_contact_candidate(
        {
            "full_name": "Ada Lovelace",
            "notes": "Card note",
            "profile_url": "example.test/ada",
        }
    )

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
    assert reviewed["extras"]["profile_url"] == "example.test/ada"
    assert any(point["kind"] == "profile_url" for point in reviewed["contact_points"])
    assert "title" not in reviewed["flat"]
