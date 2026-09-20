from app.routes.browser_agent import _fill_result_read


def test_fill_result_read_masks_sensitive_requested_and_observed_values():
    result = _fill_result_read(
        {
            "filled_count": 1,
            "skipped_count": 0,
            "verified_count": 1,
            "failed_count": 0,
            "uncertain_count": 0,
            "status": "VERIFIED",
            "results": [
                {
                    "field_id": "id-no",
                    "source_path": "identity.id_number",
                    "requested": "TESTDOC-ABC1234",
                    "observed": "TESTDOC-ABC1234",
                    "status": "VERIFIED",
                    "reason": "READBACK_MATCH",
                }
            ],
        }
    )

    row = result.results[0]
    assert row.requested != "TESTDOC-ABC1234"
    assert row.observed != "TESTDOC-ABC1234"
    assert str(row.requested).endswith("1234")
    assert str(row.observed).endswith("1234")


def test_fill_result_read_keeps_non_sensitive_values_visible():
    result = _fill_result_read(
        {
            "filled_count": 1,
            "skipped_count": 0,
            "verified_count": 1,
            "failed_count": 0,
            "uncertain_count": 0,
            "status": "VERIFIED",
            "results": [
                {
                    "field_id": "name",
                    "source_path": "identity.name",
                    "requested": "赵新悦",
                    "observed": "赵新悦",
                    "status": "VERIFIED",
                    "reason": "READBACK_MATCH",
                }
            ],
        }
    )

    assert result.results[0].requested == "赵新悦"
    assert result.results[0].observed == "赵新悦"
