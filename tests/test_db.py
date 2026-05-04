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


def test_coerce_value_reads_lob_like_values():
    lob = MagicMock()
    lob.read.return_value = "large text"

    assert OracleDB._coerce_value(lob) == "large text"
    lob.read.assert_called_once()


def test_row_to_dict_coerces_values():
    lob = MagicMock()
    lob.read.return_value = "summary"

    row = OracleDB._row_to_dict(["id", "body"], (1, lob))

    assert row == {"id": 1, "body": "summary"}
