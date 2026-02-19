from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_db_cursor() -> MagicMock:
    """Context-managed DB cursor mock for unit tests."""
    cursor = MagicMock(name="cursor")
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    return cursor


@pytest.fixture
def mock_db_connection(mock_db_cursor: MagicMock) -> MagicMock:
    """DB connection mock with cursor(), commit(), rollback(), close()."""
    conn = MagicMock(name="connection")
    conn.cursor.return_value = mock_db_cursor
    return conn
