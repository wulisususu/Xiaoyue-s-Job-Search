from __future__ import annotations

from app.profile.collection_drafts import CollectionDraftCandidate
from app.profile.extraction import (
    CollectionDraftCandidate as ContractCollectionDraftCandidate,
)
from app.profile.extraction import (
    DeterministicExtractionProvider,
    DraftCandidate,
    ExtractionMetadata,
    ProfileExtractionBundle,
    ProfileExtractionProvider,
    collection_candidate_fingerprint,
    extract_deterministic,
    scalar_candidate_fingerprint,
)

SAMPLE_TEXT = "三江学院 name@example.com 手机 13800138000"


def check_bundle_contract(bundle: ProfileExtractionBundle) -> ExtractionMetadata:
    """Shared contract assertions every ProfileExtractionProvider must satisfy."""
    assert isinstance(bundle, ProfileExtractionBundle)
    assert all(isinstance(candidate, DraftCandidate) for candidate in bundle.fields)
    assert all(
        isinstance(candidate, CollectionDraftCandidate) for candidate in bundle.collections
    )
    metadata = bundle.metadata
    assert isinstance(metadata, ExtractionMetadata)
    assert metadata.provider
    assert metadata.model
    assert metadata.prompt_version
    assert metadata.schema_version
    for candidate in bundle.fields:
        assert 0.0 <= candidate.confidence <= 1.0
    for candidate in bundle.collections:
        if candidate.confidence is not None:
            assert 0.0 <= candidate.confidence <= 1.0
    return metadata


def test_deterministic_provider_returns_bundle_with_scalar_fields_empty_collections_and_metadata():
    bundle = DeterministicExtractionProvider().extract(SAMPLE_TEXT)

    metadata = check_bundle_contract(bundle)
    assert {candidate.field_key for candidate in bundle.fields} == {
        "contact.email",
        "contact.phone",
    }
    assert bundle.collections == []
    assert metadata == ExtractionMetadata(
        provider="deterministic",
        model="deterministic-contact-v1",
        prompt_version="none",
        schema_version="deterministic-v1",
    )


def test_deterministic_provider_implements_the_runtime_protocol():
    provider = DeterministicExtractionProvider()
    assert isinstance(provider, ProfileExtractionProvider)


def test_scalar_candidate_fingerprint_is_stable_and_value_sensitive():
    first = DraftCandidate(
        field_key="contact.email",
        value="name@example.com",
        value_type="string",
        confidence=0.99,
        extractor_name="deterministic-contact-v1",
    )
    same_value = DraftCandidate(
        field_key="contact.email",
        value="name@example.com",
        value_type="string",
        confidence=0.5,
        extractor_name="other-extractor",
    )
    different_value = DraftCandidate(
        field_key="contact.email",
        value="other@example.com",
        value_type="string",
        confidence=0.99,
        extractor_name="deterministic-contact-v1",
    )
    different_field = DraftCandidate(
        field_key="contact.phone",
        value="13800138000",
        value_type="string",
        confidence=0.99,
        extractor_name="deterministic-contact-v1",
    )

    assert scalar_candidate_fingerprint(first) == scalar_candidate_fingerprint(same_value)
    assert scalar_candidate_fingerprint(first) != scalar_candidate_fingerprint(different_value)
    assert scalar_candidate_fingerprint(first) != scalar_candidate_fingerprint(different_field)
    assert len(scalar_candidate_fingerprint(first)) == 64


def test_collection_candidate_fingerprint_is_stable_and_payload_sensitive():
    first = CollectionDraftCandidate(
        kind="education",
        payload={"school": "三江学院", "major": "视觉传达设计"},
        confidence=0.9,
        extractor_name="test",
    )
    same_payload = CollectionDraftCandidate(
        kind="education",
        payload={"school": "三江学院", "major": "视觉传达设计"},
        confidence=0.1,
        extractor_name="other",
    )
    different_payload = CollectionDraftCandidate(
        kind="education",
        payload={"school": "北京大学"},
        confidence=0.9,
        extractor_name="test",
    )
    different_kind = CollectionDraftCandidate(
        kind="project",
        payload={"school": "三江学院", "major": "视觉传达设计"},
        confidence=0.9,
        extractor_name="test",
    )

    assert collection_candidate_fingerprint(first) == collection_candidate_fingerprint(same_payload)
    assert collection_candidate_fingerprint(first) != collection_candidate_fingerprint(different_payload)
    assert collection_candidate_fingerprint(first) != collection_candidate_fingerprint(different_kind)
    assert scalar_candidate_fingerprint(
        DraftCandidate("k", "v", "string", 0.9, "x")
    ) != collection_candidate_fingerprint(first)


def test_collection_draft_candidate_is_shared_between_contract_and_draft_modules():
    assert ContractCollectionDraftCandidate is CollectionDraftCandidate


def test_extract_deterministic_shim_keeps_scalar_only_compatibility():
    candidates = extract_deterministic(SAMPLE_TEXT)

    bundle = DeterministicExtractionProvider().extract(SAMPLE_TEXT)
    assert candidates == bundle.fields
