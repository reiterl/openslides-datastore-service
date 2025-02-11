from .apply_list_updates import ListUpdatesDict, apply_fields  # noqa
from .connection_handler import ConnectionHandler, DatabaseError  # noqa
from .pg_connection_handler import retry_on_db_failure  # noqa
from .sql_event_types import EVENT_TYPES  # noqa
from .sql_query_helper import SqlQueryHelper


ALL_TABLES = (
    "positions",
    "events",
    "id_sequences",
    "collectionfields",
    "events_to_collectionfields",
    "models",
    "migration_keyframes",
    "migration_keyframe_models",
    "migration_events",
    "migration_positions",
)


def setup_di():
    from datastore.shared.di import injector
    from datastore.shared.services import ReadDatabase

    from .pg_connection_handler import PgConnectionHandlerService
    from .sql_read_database_backend_service import SqlReadDatabaseBackendService

    injector.register(ConnectionHandler, PgConnectionHandlerService)
    injector.register(SqlQueryHelper, SqlQueryHelper)
    injector.register(ReadDatabase, SqlReadDatabaseBackendService)
