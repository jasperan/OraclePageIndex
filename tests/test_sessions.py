"""Tests for conversational memory graph operations."""
from unittest.mock import MagicMock
from oracle_pageindex.graph import GraphStore


def _make_graph():
    mock_db = MagicMock()
    mock_db.execute_returning.return_value = 1
    return GraphStore(mock_db), mock_db


def test_create_session():
    gs, db = _make_graph()
    sid = gs.create_session(title="Apple Q&A")
    assert sid == 1
    call_sql = db.execute_returning.call_args[0][0]
    assert "sessions" in call_sql.lower()


def test_create_turn():
    gs, db = _make_graph()
    db.execute_returning.return_value = 5
    tid = gs.create_turn(session_id=1, turn_number=1, question="What is Apple?", intent="LOOKUP")
    assert tid == 5


def test_update_turn_answer():
    gs, db = _make_graph()
    gs.update_turn_answer(turn_id=5, answer="Apple is a company.")
    db.execute.assert_called_once()
    call_sql = db.execute.call_args[0][0]
    assert "UPDATE" in call_sql.upper()


def test_insert_turn_entity():
    gs, db = _make_graph()
    gs.insert_turn_entity(turn_id=5, entity_id=42, role="PRIMARY")
    db.execute.assert_called_once()


def test_insert_turn_section():
    gs, db = _make_graph()
    gs.insert_turn_section(turn_id=5, section_id=10, rank_score=0.95)
    db.execute.assert_called_once()


def test_get_session_context():
    gs, db = _make_graph()
    db.fetchone.side_effect = [
        {"turn_number": 3},  # latest turn number
        {"turn_id": 7},      # turn_id for that turn
    ]
    db.fetchall.side_effect = [
        [{"entity_id": 1, "name": "Apple Inc.", "entity_type": "ORG", "role": "PRIMARY"}],
        [{"section_id": 9, "rank_score": 0.9}, {"section_id": 11, "rank_score": 0.8}],
    ]
    ctx = gs.get_session_context(session_id=1)
    assert len(ctx["primary_entities"]) == 1
    assert ctx["primary_entities"][0]["name"] == "Apple Inc."
    assert ctx["previous_sections"] == [9, 11]


def test_get_session_context_empty():
    gs, db = _make_graph()
    db.fetchone.return_value = {"turn_number": None}
    ctx = gs.get_session_context(session_id=999)
    assert ctx["primary_entities"] == []
    assert ctx["previous_sections"] == []


def test_list_sessions():
    gs, db = _make_graph()
    db.fetchall.return_value = [
        {"session_id": 1, "title": "Apple Q&A", "started_at": "2026-03-17"},
        {"session_id": 2, "title": "Risk Analysis", "started_at": "2026-03-17"},
    ]
    sessions = gs.list_sessions()
    assert len(sessions) == 2


def test_get_session_turns():
    gs, db = _make_graph()
    db.fetchall.return_value = [
        {"turn_id": 1, "turn_number": 1, "question": "Q1"},
        {"turn_id": 2, "turn_number": 2, "question": "Q2"},
    ]
    turns = gs.get_session_turns(session_id=1)
    assert len(turns) == 2
