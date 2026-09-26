# Retained for Python parity collection; native CTest uses explicit registrations.
from schgen.core.artifacts import is_sync_duplicate


def pytest_ignore_collect(collection_path):
    return True if is_sync_duplicate(collection_path) else None
