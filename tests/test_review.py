import json
from pathlib import Path

from business_card_watchdog.review import assess_contact_spec, build_review_submission, write_review_packet


def test_assess_contact_spec_passes_visible_identity() -> None:
    assessment = assess_contact_spec({"full_name": "Ada Lovelace", "email": "ada@example.test"})

    assert assessment.status == "pass"
    assert assessment.reasons == []


def test_assess_contact_spec_requires_name_and_identity() -> None:
    assessment = assess_contact_spec({"title": "Founder"})

    assert assessment.status == "needs_review"
    assert "full_name" in assessment.missing_fields
    assert "email_or_phone_or_organization" in assessment.missing_fields


def test_write_review_packet_is_structured(tmp_path: Path) -> None:
    assessment = assess_contact_spec({"organization": "No Name Labs"})
    packet_path = write_review_packet(
        packet_path=tmp_path / "review_packet.json",
        image_path=tmp_path / "card.png",
        spec={"organization": "No Name Labs"},
        assessment=assessment,
    )

    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    assert packet["schema"] == "business-card-watchdog.review-packet.v1"
    assert packet["assessment"]["status"] == "needs_review"
    assert packet["observed_fields"] == {"organization": "No Name Labs"}


def test_review_submission_accepts_duplicate_resolution() -> None:
    submission = build_review_submission(
        job_id="job-001",
        reviewer="operator",
        action="resolve_duplicate",
        duplicate_resolution={"decision": "merge_existing", "target_identity": "email:ada@example.test"},
    )

    assert submission["duplicate_resolution"]["decision"] == "merge_existing"


def test_review_submission_rejects_unknown_duplicate_resolution() -> None:
    try:
        build_review_submission(
            job_id="job-001",
            reviewer="operator",
            action="resolve_duplicate",
            duplicate_resolution={"decision": "invent"},
        )
    except ValueError as exc:
        assert "duplicate resolution decision" in str(exc)
    else:
        raise AssertionError("expected ValueError")
