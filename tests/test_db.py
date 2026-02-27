import pytest
from unittest.mock import patch, MagicMock
from oracle_pageindex.db import OracleDB


def test_db_init():
    db = OracleDB(user="test", password="test", dsn="localhost:1521/FREEPDB1")
    assert db.user == "test"
    assert db.dsn == "localhost:1521/FREEPDB1"
    assert db._pool is None


@patch("oracledb.create_pool")
def test_db_connect(mock_pool):
    mock_pool.return_value = MagicMock()
    db = OracleDB(user="test", password="test", dsn="localhost:1521/FREEPDB1")
    pool = db.connect()
    assert pool is not None
    mock_pool.assert_called_once()


@patch("oracledb.create_pool")
def test_db_close(mock_pool):
    mock_pool.return_value = MagicMock()
    db = OracleDB(user="test", password="test", dsn="localhost:1521/FREEPDB1")
    db.connect()
    db.close()
    assert db._pool is None
