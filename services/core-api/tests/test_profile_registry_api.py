def test_profile_definitions_expose_the_single_server_owned_registry(client):
    response = client.get("/api/profile/definitions")

    assert response.status_code == 200
    definitions = response.json()
    by_key = {item["field_key"]: item for item in definitions}
    assert len(definitions) == 18
    assert by_key["identity.name"] == {
        "field_key": "identity.name",
        "label": "姓名",
        "category": "身份信息",
        "value_type": "string",
        "multiple": False,
        "sensitive": False,
    }
    assert by_key["job.target_roles"]["value_type"] == "string_list"
    assert by_key["job.target_roles"]["multiple"] is True


def test_profile_definitions_flag_sensitive_identity_fields(client):
    response = client.get("/api/profile/definitions")
    assert response.status_code == 200
    by_key = {item["field_key"]: item for item in response.json()}
    assert by_key["identity.id_number"]["sensitive"] is True
    assert by_key["identity.birth_date"]["sensitive"] is False
