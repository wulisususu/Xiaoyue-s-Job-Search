def test_setting_round_trip(client):
    response = client.put("/api/settings/theme", json={"value": "system"})
    assert response.status_code == 200
    assert response.json() == {"key": "theme", "value": "system"}

    response = client.get("/api/settings")
    assert response.status_code == 200
    assert response.json()["theme"] == "system"


def test_settings_reject_secret_keys(client):
    response = client.put("/api/settings/openai_api_key", json={"value": "secret"})
    assert response.status_code == 400
