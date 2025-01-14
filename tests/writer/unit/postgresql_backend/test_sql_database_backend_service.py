from unittest.mock import MagicMock, patch

import pytest

from datastore.shared.di import injector
from datastore.shared.postgresql_backend import ALL_TABLES, ConnectionHandler
from datastore.shared.services import ReadDatabase
from datastore.shared.util import (
    BadCodingError,
    InvalidFormat,
    ModelDoesNotExist,
    ModelExists,
    ModelNotDeleted,
)
from datastore.writer.core.database import Database
from datastore.writer.postgresql_backend import (
    DbCreateEvent,
    DbDeleteEvent,
    DbDeleteFieldsEvent,
    DbListUpdateEvent,
    DbRestoreEvent,
    DbUpdateEvent,
    EventTranslator,
    SqlDatabaseBackendService,
)
from datastore.writer.postgresql_backend.sql_database_backend_service import (
    COLLECTION_MAX_LEN,
    COLLECTIONFIELD_MAX_LEN,
    EVENT_TYPES,
    FQID_MAX_LEN,
)
from tests import reset_di  # noqa


@pytest.fixture(autouse=True)
def provide_di(reset_di):  # noqa
    injector.register_as_singleton(ConnectionHandler, MagicMock)
    injector.register_as_singleton(ReadDatabase, MagicMock)
    injector.register_as_singleton(EventTranslator, MagicMock)
    injector.register(Database, SqlDatabaseBackendService)
    yield


@pytest.fixture()
def sql_backend(provide_di):
    yield injector.get(Database)


@pytest.fixture()
def connection(provide_di):
    yield injector.get(ConnectionHandler)


@pytest.fixture()
def read_db(provide_di):
    yield injector.get(ReadDatabase)


@pytest.fixture()
def event_translator(provide_di):
    yield injector.get(EventTranslator)


def test_sql_backend_creation(sql_backend):
    assert bool(sql_backend)


def test_get_context(sql_backend, connection):
    connection.get_connection_context = MagicMock(return_value="my_return_value")

    assert sql_backend.get_context() == "my_return_value"


def test_json(sql_backend, connection):
    connection.to_json = tj = MagicMock(return_value="my_return_value")

    assert sql_backend.json("my_data") == "my_return_value"
    tj.assert_called_with("my_data")


class TestExistsQuery:
    def test_exists_query_did_not_found_someting(self, sql_backend, connection):
        connection.query_single_value = MagicMock(return_value=False)

        assert sql_backend.exists_query("", "", None) is False

    def test_exists_query_found_something(self, sql_backend, connection):
        connection.query_single_value = MagicMock(return_value=True)

        assert sql_backend.exists_query("", "", None)

    def test_exists_query_passed_arguments(self, sql_backend, connection):
        connection.query_single_value = qsv = MagicMock(return_value=None)
        args = MagicMock()

        sql_backend.exists_query("", "", args)

        assert qsv.call_args.args[1] == args

    def test_exists_query_table_name_and_conditions(self, sql_backend, connection):
        connection.query_single_value = qsv = MagicMock(return_value=None)

        sql_backend.exists_query("my_table", "some_conditions", None)

        assert "my_table" in qsv.call_args.args[0]
        assert "some_conditions" in qsv.call_args.args[0]


class TestInsertEvents:
    def test_insert_no_events(self, sql_backend):
        sql_backend.create_position = cp = MagicMock()
        with pytest.raises(BadCodingError):
            sql_backend.insert_events([], 1, {}, 1)
        cp.assert_not_called()

    def test_insert_invalid_event(self, sql_backend):
        sql_backend.create_position = cp = MagicMock()
        with pytest.raises(BadCodingError):
            sql_backend.insert_event({}, 1, 1)
        cp.assert_not_called()

    def test_set_position(self, sql_backend):
        sql_backend.create_position = MagicMock(return_value=239)
        sql_backend.insert_event = MagicMock()
        event = MagicMock()
        event.fqid = "a/1"

        position, _ = sql_backend.insert_events([event], 1, {}, 1)

        assert position == 239

    def test_call_insert_event(self, sql_backend, event_translator):
        sql_backend.create_position = MagicMock()
        sql_backend.insert_event = ie = MagicMock()
        event_translator.translate = translate = MagicMock(side_effect=lambda x: [x])
        event1 = MagicMock()
        event1.fqid = "a/1"
        event2 = MagicMock()
        event2.fqid = "a/2"

        sql_backend.insert_events([event1, event2], 1, {}, 1)

        assert ie.call_count == 2
        assert ie.call_args_list[0].args[0] == event1
        assert ie.call_args_list[1].args[0] == event2

        assert translate.call_count == 2
        assert translate.call_args_list[0].args[0] == event1
        assert translate.call_args_list[1].args[0] == event2

    def test_call_get_modified_fields(self, sql_backend, event_translator):
        sql_backend.create_position = MagicMock()
        sql_backend.insert_event = MagicMock()
        event_translator.translate = MagicMock(side_effect=lambda x: [x])
        event1 = MagicMock()
        event1.fqid = "a/1"
        value1 = MagicMock()
        event1.get_modified_fields = gmf1 = MagicMock(return_value={"f1": value1})
        event2 = MagicMock()
        event2.fqid = "a/2"
        value2 = MagicMock()
        event2.get_modified_fields = gmf2 = MagicMock(return_value={"f2": value2})

        _, modified_models = sql_backend.insert_events([event1, event2], 1, {}, 1)

        assert modified_models[event1.fqid] == {"f1": value1}
        assert modified_models[event2.fqid] == {"f2": value2}
        gmf1.assert_called_once()
        gmf2.assert_called_once()

    def test_fqid_too_long(self, sql_backend, event_translator):
        event_translator.translate = MagicMock(side_effect=lambda x: [x])
        event = MagicMock()
        event.fqid = "a/" + "1" * FQID_MAX_LEN
        sql_backend.create_position = MagicMock()

        with pytest.raises(InvalidFormat) as e:
            sql_backend.insert_events([event], 1, {}, 1)

        assert event.fqid in e.value.msg


def test_create_position(sql_backend, connection):
    sql_backend.json = json = MagicMock(side_effect=lambda data: data)
    connection.query_single_value = MagicMock(return_value=2844)
    connection.execute = execute = MagicMock()

    position = sql_backend.create_position(1, {"some": "data", "is": ["given"]}, 42)

    assert position == 2844
    execute.assert_called_once()
    json.assert_called_once()


class TestInsertEventDispatching:
    def test_create_event(self, sql_backend):
        sql_backend.insert_create_event = ie = MagicMock()
        event = DbCreateEvent("a/1", {"f": "Value"})
        position = MagicMock()
        weight = MagicMock()

        sql_backend.insert_event(event, position, weight)

        ie.assert_called_with(event, position, weight)

    def test_update_event(self, sql_backend):
        sql_backend.insert_update_event = ie = MagicMock()
        event = DbUpdateEvent("a/1", {"f": "Value"})
        position = MagicMock()
        weight = MagicMock()

        sql_backend.insert_event(event, position, weight)

        ie.assert_called_with(event, position, weight)

    def test_list_update_event(self, sql_backend):
        sql_backend.insert_list_update_event = ie = MagicMock()
        event = DbListUpdateEvent("a/1", {}, {}, {})
        position = MagicMock()
        weight = MagicMock()

        sql_backend.insert_event(event, position, weight)

        ie.assert_called_with(event, position, weight)

    def test_delete_fields_event(self, sql_backend):
        sql_backend.insert_delete_fields_event = ie = MagicMock()
        event = DbDeleteFieldsEvent("a/1", ["f"])
        position = MagicMock()
        weight = MagicMock()

        sql_backend.insert_event(event, position, weight)

        ie.assert_called_with(event, position, weight)

    def test_delete_event(self, sql_backend):
        sql_backend.insert_delete_event = ie = MagicMock()
        event = DbDeleteEvent("a/1", ["f"])
        position = MagicMock()
        weight = MagicMock()

        sql_backend.insert_event(event, position, weight)

        ie.assert_called_with(event, position, weight)

    def test_restore_event(self, sql_backend):
        sql_backend.insert_restore_event = ie = MagicMock()
        event = DbRestoreEvent("a/1", ["f"])
        position = MagicMock()
        weight = MagicMock()

        sql_backend.insert_event(event, position, weight)

        ie.assert_called_with(event, position, weight)


def test_insert_db_event(sql_backend, connection):
    event_id = MagicMock()
    event = MagicMock()
    arguments = MagicMock()
    position = MagicMock()
    connection.query_single_value = qsv = MagicMock(return_value=event_id)
    sql_backend.attach_modified_fields_to_event = amfte = MagicMock()

    sql_backend.insert_db_event(event, arguments, position)

    assert qsv.call_args.args[1] == arguments
    amfte.assert_called_with(event_id, event, position)


class TestAttachModifiedFieldsToEvents:
    def test_attach_modified_fields_to_event(self, sql_backend):
        modified_collectionfields = MagicMock()
        collection_ids = MagicMock()
        event_id = MagicMock()
        event = MagicMock()
        position = MagicMock()
        sql_backend.get_modified_collectionfields_from_event = gmcfe = MagicMock(
            return_value=modified_collectionfields
        )
        sql_backend.insert_modified_collectionfields_into_db = imcid = MagicMock(
            return_value=collection_ids
        )
        sql_backend.connect_events_and_collection_fields = ceacf = MagicMock()

        sql_backend.attach_modified_fields_to_event(event_id, event, position)

        gmcfe.assert_called_with(event)
        imcid.assert_called_with(modified_collectionfields, position)
        ceacf.assert_called_with(event_id, collection_ids)

    def test_get_modified_collectionfields_from_event(self, sql_backend):
        event = MagicMock()
        field = MagicMock()
        event.get_modified_fields = MagicMock(return_value=[field])
        event.fqid = MagicMock()
        with patch(
            "datastore.writer.postgresql_backend.sql_database_backend_service.collectionfield_from_fqid_and_field"  # noqa
        ) as cffaf:
            result = MagicMock()
            cffaf.side_effect = lambda x, y: result

            assert sql_backend.get_modified_collectionfields_from_event(event) == [
                result
            ]

            cffaf.assert_called_with(event.fqid, field)

    def test_insert_modified_collectionfields_into_db(self, sql_backend, connection):
        collectionfield_ids = MagicMock()
        connection.query_list_of_single_values = qlosv = MagicMock(
            return_value=collectionfield_ids
        )
        collectionfield = MagicMock()
        position = MagicMock()

        sql_backend.insert_modified_collectionfields_into_db(
            [collectionfield], position
        )
        assert qlosv.call_args.args[1] == [collectionfield, position]

    def test_insert_modified_collectionfields_into_db_too_long(
        self, sql_backend, connection
    ):
        connection.query_list_of_single_values = qlosv = MagicMock()
        collectionfield = "c/" + "f" * COLLECTIONFIELD_MAX_LEN

        with pytest.raises(InvalidFormat) as e:
            sql_backend.insert_modified_collectionfields_into_db(
                [collectionfield], MagicMock()
            )

        assert collectionfield in e.value.msg
        qlosv.assert_not_called()

    def test_connect_events_and_collection_fields(self, sql_backend, connection):
        collectionfield_id = MagicMock()
        connection.execute = ex = MagicMock()
        event_id = MagicMock()

        sql_backend.connect_events_and_collection_fields(event_id, [collectionfield_id])

        ex.assert_called_once()
        assert ex.call_args.args[1] == [event_id, collectionfield_id]


class TestInsertCreateEvent:
    def test_raise_model_exists(self, sql_backend):
        sql_backend.exists_query = MagicMock(return_value=True)
        event = MagicMock()
        event.fqid = "a/1"

        with pytest.raises(ModelExists) as e:
            sql_backend.insert_create_event(event, MagicMock(), MagicMock())

        assert event.fqid == e.value.fqid

    def test_insert(self, sql_backend, connection):
        sql_backend.exists_query = MagicMock(return_value=False)
        sql_backend.json = json = MagicMock(side_effect=lambda x: x)
        sql_backend.insert_db_event = ide = MagicMock()
        sql_backend.create_model = cm = MagicMock()
        connection.execute = ex = MagicMock()
        event = MagicMock()
        event.fqid = "a/1"
        event.field_data = {"f": "test_data"}
        event.get_modified_fields = MagicMock(return_value="f")
        position = MagicMock()
        weight = MagicMock()

        sql_backend.insert_create_event(event, position, weight)

        ex.assert_called()
        ide.assert_called_with(
            event,
            [position, event.fqid, EVENT_TYPES.CREATE, {"f": "test_data"}, weight],
            position,
        )
        json.assert_called_once()
        cm.assert_called_once()


def test_insert_update_event(sql_backend, connection):
    sql_backend.assert_exists = ae = MagicMock()
    sql_backend.json = json = MagicMock(side_effect=lambda x: x)
    sql_backend.insert_db_event = ide = MagicMock()
    sql_backend.update_model = um = MagicMock()
    event = MagicMock()
    event.fqid = "a/1"
    event.field_data = "test_data"
    event.get_modified_fields = MagicMock(return_value="f")
    position = MagicMock()
    weight = MagicMock()

    sql_backend.insert_update_event(event, position, weight)

    ae.assert_called_with(event.fqid)
    ide.assert_called_with(
        event, [position, event.fqid, EVENT_TYPES.UPDATE, "test_data", weight], position
    )
    json.assert_called_once()
    um.assert_called_once()


def test_insert_delete_fields_event(sql_backend, connection):
    sql_backend.assert_exists = ae = MagicMock()
    sql_backend.json = json = MagicMock(side_effect=lambda x: x)
    sql_backend.insert_db_event = ide = MagicMock()
    sql_backend.update_model = um = MagicMock()
    event = MagicMock()
    event.fqid = "a/1"
    event.fields = ["f1", "f2"]
    position = MagicMock()
    weight = MagicMock()

    sql_backend.insert_delete_fields_event(event, position, weight)

    ae.assert_called_with(event.fqid)
    ide.assert_called_with(
        event,
        [position, event.fqid, EVENT_TYPES.DELETE_FIELDS, event.fields, weight],
        position,
    )
    json.assert_called_once()
    um.assert_called_once()


def test_insert_delete_event(sql_backend, connection):
    sql_backend.assert_exists = ae = MagicMock()
    sql_backend.json = json = MagicMock(side_effect=lambda x: x)
    sql_backend.insert_db_event = ide = MagicMock()
    sql_backend.delete_model = dm = MagicMock()
    event = MagicMock()
    event.fqid = "a/1"
    position = MagicMock()
    weight = MagicMock()

    sql_backend.insert_delete_event(event, position, weight)

    ae.assert_called_with(event.fqid)
    ide.assert_called_with(
        event, [position, event.fqid, EVENT_TYPES.DELETE, None, weight], position
    )
    json.assert_called_once()
    dm.assert_called_with(event.fqid, position)


def test_assert_exists(sql_backend):
    sql_backend.exists_query = MagicMock(return_value=False)
    fqid = "a/1"

    with pytest.raises(ModelDoesNotExist) as e:
        sql_backend.assert_exists(fqid)
    assert e.value.fqid == fqid


def test_insert_restore_event_raises_model_not_deleted(sql_backend, connection):
    sql_backend.exists_query = MagicMock(return_value=False)
    event = MagicMock()
    event.fqid = "a/1"

    with pytest.raises(ModelNotDeleted) as e:
        sql_backend.insert_restore_event(event, MagicMock(), MagicMock())
    assert e.value.fqid == event.fqid


def test_insert_restore_event(sql_backend, connection):
    sql_backend.exists_query = eq = MagicMock(return_value=True)
    sql_backend.json = json = MagicMock(side_effect=lambda x: x)
    sql_backend.insert_db_event = ide = MagicMock()
    sql_backend.restore_model = rm = MagicMock()
    event = MagicMock()
    event.fqid = "a/1"
    position = MagicMock()
    weight = MagicMock()

    sql_backend.insert_restore_event(event, position, weight)

    eq.assert_called_once()
    ide.assert_called_with(
        event, [position, event.fqid, EVENT_TYPES.RESTORE, None, weight], position
    )
    json.assert_called_once()
    rm.assert_called_with(event.fqid, position)


class TestReserveNextIds:
    def test_wrong_amount(self, sql_backend):
        with pytest.raises(InvalidFormat):
            sql_backend.reserve_next_ids("my_collection", 0)

    def test_empty_collection(self, sql_backend):
        with pytest.raises(InvalidFormat):
            sql_backend.reserve_next_ids("", 1)

    def test_collection_too_long(self, sql_backend):
        with pytest.raises(InvalidFormat):
            sql_backend.reserve_next_ids("x" * (COLLECTION_MAX_LEN + 1), 1)

    def test_initial_collection_query(self, sql_backend, connection):
        connection.query_single_value = qsv = MagicMock(return_value=4)

        result = sql_backend.reserve_next_ids("my_collection", 3)

        assert result == [1, 2, 3]
        args = qsv.call_args.args[1]
        assert args == ["my_collection", 4]

    def test_collection_query(self, sql_backend, connection):
        connection.query_single_value = qsv = MagicMock(return_value=7)

        result = sql_backend.reserve_next_ids("my_collection", 3)

        assert result == [4, 5, 6]
        args = qsv.call_args.args[1]
        assert args == ["my_collection", 4]


def test_truncate_db(sql_backend, connection):
    connection.execute = ex = MagicMock()
    sql_backend.truncate_db()
    assert ex.call_count == len(ALL_TABLES) + 3  # account for sequence resets
    assert all(
        "DELETE FROM" in call.args[0] for call in ex.call_args_list[: len(ALL_TABLES)]
    )
    assert all(
        "RESTART" in call.args[0]
        for call in ex.call_args_list[len(ALL_TABLES) + 1 :]  # noqa: E203
    )
