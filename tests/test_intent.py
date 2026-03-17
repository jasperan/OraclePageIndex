"""Tests for LLM-based query intent classification."""
from unittest.mock import patch
from oracle_pageindex.llm import OllamaClient
from oracle_pageindex.models import QueryIntent


def _make_client():
    return OllamaClient(base_url="http://localhost:11434", model="test")


def test_classify_intent_lookup():
    client = _make_client()
    with patch.object(client, "chat", return_value='{"intent": "LOOKUP", "entities": ["Apple"]}'):
        intent, entities = client.classify_intent("What is Apple?")
    assert intent == QueryIntent.LOOKUP
    assert "Apple" in entities


def test_classify_intent_relationship():
    client = _make_client()
    with patch.object(client, "chat", return_value='{"intent": "RELATIONSHIP", "entities": ["Apple", "Samsung"]}'):
        intent, entities = client.classify_intent("How does Apple relate to Samsung?")
    assert intent == QueryIntent.RELATIONSHIP
    assert len(entities) == 2


def test_classify_intent_exploration():
    client = _make_client()
    with patch.object(client, "chat", return_value='{"intent": "EXPLORATION", "entities": ["risk factors"]}'):
        intent, entities = client.classify_intent("What are the main risks?")
    assert intent == QueryIntent.EXPLORATION


def test_classify_intent_comparison():
    client = _make_client()
    with patch.object(client, "chat", return_value='{"intent": "COMPARISON", "entities": ["Apple", "Microsoft"]}'):
        intent, entities = client.classify_intent("Compare Apple vs Microsoft")
    assert intent == QueryIntent.COMPARISON


def test_classify_intent_temporal():
    client = _make_client()
    with patch.object(client, "chat", return_value='{"intent": "TEMPORAL", "entities": ["risk factors"]}'):
        intent, entities = client.classify_intent("What changed between 2023 and 2024?")
    assert intent == QueryIntent.TEMPORAL


def test_classify_intent_hierarchical():
    client = _make_client()
    with patch.object(client, "chat", return_value='{"intent": "HIERARCHICAL", "entities": ["Financial Statements"]}'):
        intent, entities = client.classify_intent("Give me details about the Financial Statements section")
    assert intent == QueryIntent.HIERARCHICAL


def test_classify_intent_fallback_on_bad_json():
    client = _make_client()
    with patch.object(client, "chat", return_value="I don't understand"):
        intent, entities = client.classify_intent("Something weird")
    assert intent == QueryIntent.EXPLORATION
    assert entities == []


def test_classify_intent_fallback_on_exception():
    client = _make_client()
    with patch.object(client, "chat", side_effect=Exception("connection error")):
        intent, entities = client.classify_intent("test")
    assert intent == QueryIntent.EXPLORATION
    assert entities == []


def test_classify_intent_unknown_intent_string():
    client = _make_client()
    with patch.object(client, "chat", return_value='{"intent": "UNKNOWN_TYPE", "entities": ["X"]}'):
        intent, entities = client.classify_intent("test")
    assert intent == QueryIntent.EXPLORATION
    assert entities == ["X"]
