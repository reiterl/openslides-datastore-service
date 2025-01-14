import copy

import pytest

from datastore.shared.flask_frontend import ERROR_CODES
from datastore.writer.flask_frontend.routes import WRITE_URL
from tests.util import assert_error_response, assert_response_code
from tests.writer.system.util import (
    assert_model,
    assert_modified_fields,
    assert_no_model,
)

from .test_write import create_model


@pytest.fixture()
def data():
    yield copy.deepcopy(
        {
            "user_id": 1,
            "information": {},
            "locked_fields": {},
            "events": [{"type": "create", "fqid": "a/1", "fields": {"f": 1}}],
        }
    )


def test_create_update(json_client, data, redis_connection):
    field_data = [True, None, {"test": "value"}]
    data["events"].append(
        {
            "type": "update",
            "fqid": "a/1",
            "fields": {"f": None, "another_field": field_data},
        }
    )
    response = json_client.post(WRITE_URL, data)
    assert_response_code(response, 201)
    assert_model("a/1", {"another_field": field_data}, 1)
    assert_modified_fields(redis_connection, {"a/1": ["f", "another_field"]})


def test_update_and_list_update(json_client, data, redis_connection, reset_redis_data):
    data["events"][0]["fields"]["f"] = [1]
    create_model(json_client, data, redis_connection, reset_redis_data)

    data["events"][0] = {
        "type": "update",
        "fqid": "a/1",
        "fields": {"g": [2]},
        "list_fields": {"add": {"f": [2]}},
    }
    response = json_client.post(WRITE_URL, data)
    assert_response_code(response, 201)
    assert_model("a/1", {"f": [1, 2], "g": [2]}, 2)
    assert_modified_fields(redis_connection, {"a/1": ["f", "g"]}, meta_deleted=False)


def test_list_update_with_create(json_client, data, redis_connection, reset_redis_data):
    data["events"].append(
        {
            "type": "update",
            "fqid": "a/1",
            "list_fields": {"add": {"g": [2]}},
        }
    )
    response = json_client.post(WRITE_URL, data)
    assert_response_code(response, 201)
    assert_model("a/1", {"f": 1, "g": [2]}, 1)
    assert_modified_fields(redis_connection, {"a/1": ["f", "g"]})


def test_create_delete(json_client, data, redis_connection, reset_redis_data):
    data["events"].append({"type": "delete", "fqid": "a/1"})
    response = json_client.post(WRITE_URL, data)
    assert_response_code(response, 201)
    assert_no_model("a/1")
    assert_modified_fields(redis_connection, {"a/1": ["f"]})


def test_create_delete_restore(json_client, data, redis_connection):
    data["events"].append({"type": "delete", "fqid": "a/1"})
    data["events"].append({"type": "restore", "fqid": "a/1"})
    response = json_client.post(WRITE_URL, data)
    assert_response_code(response, 201)
    assert_model("a/1", {"f": 1}, 1)
    assert_modified_fields(redis_connection, {"a/1": ["f"]})


def test_create_delete_restore_different_positions(
    json_client, data, redis_connection, reset_redis_data
):
    create_model(json_client, data, redis_connection, reset_redis_data)

    data["events"][0] = {"type": "delete", "fqid": "a/1"}
    response = json_client.post(WRITE_URL, data)
    assert_response_code(response, 201)
    assert_no_model("a/1")
    assert_modified_fields(redis_connection, {"a/1": ["f"]})
    reset_redis_data()

    data["events"][0] = {"type": "restore", "fqid": "a/1"}

    response = json_client.post(WRITE_URL, data)
    assert_response_code(response, 201)
    assert_model("a/1", {"f": 1}, 3)
    assert_modified_fields(redis_connection, {"a/1": ["f"]})


def test_delete_restore_delete_restore(
    json_client, data, redis_connection, reset_redis_data
):
    create_model(json_client, data, redis_connection, reset_redis_data)

    data["events"][0] = {"type": "delete", "fqid": "a/1"}
    data["events"].append({"type": "restore", "fqid": "a/1"})
    data["events"].append({"type": "delete", "fqid": "a/1"})
    data["events"].append({"type": "restore", "fqid": "a/1"})
    response = json_client.post(WRITE_URL, data)
    assert_response_code(response, 201)
    assert_model("a/1", {"f": 1}, 2)
    assert_modified_fields(redis_connection, {"a/1": ["f"]})


def test_update_delete_restore_update(
    json_client, data, redis_connection, reset_redis_data
):
    create_model(json_client, data, redis_connection, reset_redis_data)

    data["events"][0] = {
        "type": "update",
        "fqid": "a/1",
        "fields": {"another": "value", "f": None},
    }
    data["events"].append({"type": "delete", "fqid": "a/1"})
    data["events"].append({"type": "restore", "fqid": "a/1"})
    data["events"].append(
        {"type": "update", "fqid": "a/1", "fields": {"third_field": ["my", "list"]}}
    )
    response = json_client.post(WRITE_URL, data)
    assert_response_code(response, 201)
    assert_model("a/1", {"another": "value", "third_field": ["my", "list"]}, 2)
    assert_modified_fields(redis_connection, {"a/1": ["f", "another", "third_field"]})


def test_delete_update(json_client, data, redis_connection, reset_redis_data):
    create_model(json_client, data, redis_connection, reset_redis_data)

    data["events"][0] = {"type": "delete", "fqid": "a/1"}
    data["events"].append(
        {
            "type": "update",
            "fqid": "a/1",
            "fields": {"f": 42},
        }
    )
    response = json_client.post(WRITE_URL, data)
    assert_error_response(response, ERROR_CODES.MODEL_DOES_NOT_EXIST)
