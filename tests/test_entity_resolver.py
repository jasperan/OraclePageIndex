"""Tests for vector-assisted entity resolution."""
from unittest.mock import MagicMock
from oracle_pageindex.entity_resolver import EntityResolver


def _make_resolver(enabled=True):
    mock_llm = MagicMock()
    mock_graph = MagicMock()
    config = {
        "enabled": enabled,
        "embedding_model": "nomic-embed-text",
        "similarity_threshold": 0.3,
        "auto_confirm_threshold": 0.15,
    }
    return EntityResolver(mock_llm, mock_graph, config), mock_llm, mock_graph


def test_find_candidates():
    resolver, llm, graph = _make_resolver()
    llm.embed.return_value = [0.1, 0.2, 0.3]
    graph.find_similar_entities.return_value = [
        {"entity_id": 2, "name": "Apple", "entity_type": "ORGANIZATION", "distance": 0.1}
    ]
    candidates = resolver.find_candidates(
        entity_id=1, name="Apple Inc.", entity_type="ORGANIZATION"
    )
    assert len(candidates) == 1
    assert candidates[0]["distance"] == 0.1
    llm.embed.assert_called_once_with("Apple Inc.", model="nomic-embed-text")


def test_find_candidates_disabled():
    resolver, llm, _ = _make_resolver(enabled=False)
    candidates = resolver.find_candidates(entity_id=1, name="X", entity_type="Y")
    assert candidates == []
    llm.embed.assert_not_called()


def test_find_candidates_no_embedding():
    resolver, llm, graph = _make_resolver()
    llm.embed.return_value = []
    candidates = resolver.find_candidates(entity_id=1, name="X", entity_type="Y")
    assert candidates == []
    graph.find_similar_entities.assert_not_called()


def test_should_confirm_auto():
    resolver, _, _ = _make_resolver()
    assert resolver.should_confirm(distance=0.08) == "auto"


def test_should_confirm_llm():
    resolver, _, _ = _make_resolver()
    assert resolver.should_confirm(distance=0.22) == "llm"


def test_should_confirm_reject():
    resolver, _, _ = _make_resolver()
    assert resolver.should_confirm(distance=0.35) == "reject"


def test_should_confirm_boundary_auto():
    resolver, _, _ = _make_resolver()
    # Exactly at auto_confirm_threshold (0.15) should be 'llm', not 'auto'
    assert resolver.should_confirm(distance=0.15) == "llm"


def test_should_confirm_boundary_reject():
    resolver, _, _ = _make_resolver()
    # Exactly at similarity_threshold (0.3) should be 'reject'
    assert resolver.should_confirm(distance=0.3) == "reject"


def test_llm_confirm_yes():
    resolver, llm, _ = _make_resolver()
    llm.chat.return_value = "YES"
    confirmed = resolver.llm_confirm(
        {"name": "Apple Inc.", "entity_type": "ORGANIZATION"},
        {"name": "AAPL", "entity_type": "ORGANIZATION"},
    )
    assert confirmed is True


def test_llm_confirm_no():
    resolver, llm, _ = _make_resolver()
    llm.chat.return_value = "NO, these are different"
    confirmed = resolver.llm_confirm(
        {"name": "Apple Inc.", "entity_type": "ORGANIZATION"},
        {"name": "Apple Records", "entity_type": "ORGANIZATION"},
    )
    assert confirmed is False


def test_llm_confirm_exception():
    resolver, llm, _ = _make_resolver()
    llm.chat.side_effect = RuntimeError("LLM down")
    confirmed = resolver.llm_confirm(
        {"name": "A", "entity_type": "X"},
        {"name": "B", "entity_type": "X"},
    )
    assert confirmed is False


def test_resolve_entity_disabled():
    resolver, llm, _ = _make_resolver(enabled=False)
    result = resolver.resolve_entity(entity_id=1, name="X", entity_type="Y")
    assert result == []
    llm.embed.assert_not_called()


def test_resolve_entity_auto_confirm():
    resolver, llm, graph = _make_resolver()
    llm.embed.return_value = [0.1, 0.2]
    graph.find_similar_entities.return_value = [
        {"entity_id": 2, "name": "Apple", "entity_type": "ORGANIZATION", "distance": 0.05}
    ]
    resolver.resolve_entity(entity_id=1, name="Apple Inc.", entity_type="ORGANIZATION")
    graph.insert_entity_alias.assert_called_once()
    graph.update_entity_canonical.assert_called_once_with(1, 2)
    # Auto-confirm: confirmed=0
    call_kwargs = graph.insert_entity_alias.call_args
    assert call_kwargs[1]["confirmed"] == 0


def test_resolve_entity_llm_confirm():
    resolver, llm, graph = _make_resolver()
    llm.embed.return_value = [0.1, 0.2]
    graph.find_similar_entities.return_value = [
        {"entity_id": 2, "name": "AAPL", "entity_type": "ORGANIZATION", "distance": 0.22}
    ]
    llm.chat.return_value = "YES"
    resolver.resolve_entity(entity_id=1, name="Apple Inc.", entity_type="ORGANIZATION")
    graph.insert_entity_alias.assert_called_once()
    # LLM-confirmed: confirmed=1
    call_kwargs = graph.insert_entity_alias.call_args
    assert call_kwargs[1]["confirmed"] == 1


def test_resolve_entity_llm_reject():
    resolver, llm, graph = _make_resolver()
    llm.embed.return_value = [0.1, 0.2]
    graph.find_similar_entities.return_value = [
        {"entity_id": 2, "name": "Apple Records", "entity_type": "ORGANIZATION", "distance": 0.22}
    ]
    llm.chat.return_value = "NO"
    result = resolver.resolve_entity(entity_id=1, name="Apple Inc.", entity_type="ORGANIZATION")
    assert result == []
    graph.insert_entity_alias.assert_not_called()


def test_resolve_entity_distance_reject():
    resolver, llm, graph = _make_resolver()
    llm.embed.return_value = [0.1, 0.2]
    graph.find_similar_entities.return_value = [
        {"entity_id": 2, "name": "Orange", "entity_type": "ORGANIZATION", "distance": 0.5}
    ]
    result = resolver.resolve_entity(entity_id=1, name="Apple Inc.", entity_type="ORGANIZATION")
    assert result == []
    graph.insert_entity_alias.assert_not_called()


def test_resolve_all_disabled():
    resolver, llm, graph = _make_resolver(enabled=False)
    result = resolver.resolve_all_new_entities([1, 2, 3])
    assert result == {"resolved": 0, "total": 3}


def test_resolve_all_batch():
    resolver, llm, graph = _make_resolver()
    graph.get_all_entities.return_value = [
        {"entity_id": 1, "name": "Apple Inc.", "entity_type": "ORG"},
        {"entity_id": 2, "name": "Apple", "entity_type": "ORG"},
    ]
    llm.embed.return_value = [0.1]
    graph.find_similar_entities.return_value = [
        {"entity_id": 2, "name": "Apple", "entity_type": "ORG", "distance": 0.05}
    ]
    result = resolver.resolve_all_new_entities([1])
    assert result["resolved"] == 1


def test_resolve_all_missing_entity():
    resolver, llm, graph = _make_resolver()
    graph.get_all_entities.return_value = [
        {"entity_id": 1, "name": "Apple Inc.", "entity_type": "ORG"},
    ]
    llm.embed.return_value = [0.1]
    graph.find_similar_entities.return_value = []
    # Entity ID 99 doesn't exist in the map
    result = resolver.resolve_all_new_entities([99])
    assert result["resolved"] == 0
    assert result["total"] == 1


def test_init_with_none_config():
    resolver = EntityResolver(MagicMock(), MagicMock(), None)
    assert resolver.enabled is False
    assert resolver.embedding_model == "nomic-embed-text"
    assert resolver.similarity_threshold == 0.3
    assert resolver.auto_confirm_threshold == 0.15
