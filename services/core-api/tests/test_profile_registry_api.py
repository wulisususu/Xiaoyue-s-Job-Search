def test_profile_definitions_expose_the_single_server_owned_registry(client):
    response = client.get("/api/profile/definitions")

    assert response.status_code == 200
    definitions = response.json()
    by_key = {item["field_key"]: item for item in definitions}
    assert len(definitions) == 13
    assert by_key["identity.name"] == {
        "field_key": "identity.name",
        "label": "姓名",
        "category": "身份信息",
        "value_type": "string",
        "multiple": False,
    }
    assert by_key["job.target_roles"]["value_type"] == "string_list"
    assert by_key["job.target_roles"]["multiple"] is True
