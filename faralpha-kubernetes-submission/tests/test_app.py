import importlib
import sys
from unittest.mock import MagicMock

import pytest


@pytest.fixture()
def client(monkeypatch):
    fake_collection = MagicMock()
    fake_collection.find.return_value = [{"sampleKey": "sampleValue"}]
    fake_db = MagicMock()
    fake_db.__getitem__.return_value = fake_collection
    fake_client = MagicMock()
    fake_client.get_default_database.return_value = fake_db
    fake_client.__getitem__.return_value = fake_db

    pymongo = MagicMock()
    pymongo.MongoClient.return_value = fake_client
    pymongo.errors.PyMongoError = Exception
    monkeypatch.setitem(sys.modules, "pymongo", pymongo)

    if "app" in sys.modules:
        del sys.modules["app"]
    app_module = importlib.import_module("app")
    app_module.app.config.update(TESTING=True)
    yield app_module.app.test_client(), fake_collection


def test_root_returns_welcome_message(client):
    test_client, _ = client
    response = test_client.get("/")
    assert response.status_code == 200
    assert response.get_data(as_text=True).startswith(
        "Welcome to the Flask app! The current time is:"
    )


def test_post_inserts_json(client):
    test_client, collection = client
    response = test_client.post("/data", json={"sampleKey": "sampleValue"})
    assert response.status_code == 201
    assert response.get_json() == {"status": "Data inserted"}
    collection.insert_one.assert_called_once_with({"sampleKey": "sampleValue"})


def test_get_returns_documents_without_id(client):
    test_client, _ = client
    response = test_client.get("/data")
    assert response.status_code == 200
    assert response.get_json() == [{"sampleKey": "sampleValue"}]


def test_post_rejects_non_object_json(client):
    test_client, _ = client
    response = test_client.post("/data", json=["not", "an", "object"])
    assert response.status_code == 400
