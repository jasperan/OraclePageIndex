import pytest
from unittest.mock import MagicMock, call

from oracle_pageindex.llm import OllamaError
from oracle_pageindex.models import GraphQuery, QueryIntent, QueryResult, TraversalStep
from oracle_pageindex.query import QueryEngine, MAX_QUERY_LENGTH


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

def _make_graph_query(**overrides):
    defaults = {
        "sql": "SELECT 1",
        "params": {},
        "purpose": "test",
        "rows_returned": 1,
        "execution_ms": 0.5,
    }
    defaults.update(overrides)
    return GraphQuery(**defaults)


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    # Default: LOOKUP intent with one entity
    llm.classify_intent.return_value = (QueryIntent.LOOKUP, ["Apple"])
    llm.chat.return_value = "Apple's revenue was $100B."
    return llm


@pytest.fixture
def mock_graph():
    graph = MagicMock()
    # Default returns for all methods used by query engine
    graph.get_all_entities.return_value = [
        {"entity_id": 1, "name": "Apple", "entity_type": "ORGANIZATION", "description": "Tech company"},
        {"entity_id": 2, "name": "Revenue", "entity_type": "METRIC", "description": "Income"},
    ]
    graph.get_entity_sections.return_value = []
    graph.get_related_entities.return_value = []
    graph.get_all_documents.return_value = []
    graph.get_document_sections.return_value = []

    # Multi-hop traversal defaults
    graph.traverse_entity_neighborhood.return_value = {
        "sections": [
            {"section_id": 1, "title": "Revenue Overview", "text_content": "Apple revenue...",
             "depth_level": 0, "relevance": "DEFINES", "doc_name": "10K.pdf"},
        ],
        "entities": [
            {"entity_id": 2, "name": "Revenue", "entity_type": "METRIC"},
        ],
        "graph_query": _make_graph_query(purpose="neighborhood"),
    }
    graph.find_entity_paths.return_value = {
        "paths": [
            {"source_name": "Apple", "mid_id": 3, "mid_name": "iPhone",
             "mid_type": "TECHNOLOGY", "r1_type": "PRODUCES", "target_name": "Revenue",
             "r2_type": "GENERATES"},
        ],
        "graph_query": _make_graph_query(purpose="path finding"),
    }
    graph.get_multi_hop_entities.return_value = {
        "entities": [
            {"entity_id": 3, "name": "iPhone", "entity_type": "TECHNOLOGY",
             "relationship": "PRODUCES", "hops": 1},
        ],
        "graph_query": _make_graph_query(purpose="multi-hop"),
    }
    graph.traverse_section_descendants.return_value = [
        {"section_id": 10, "title": "Q1 Details", "depth_level": 1, "tree_level": 1},
    ]

    # Session management defaults (Task 10)
    graph.create_session.return_value = 1
    graph.create_turn.return_value = 1
    graph.get_session_context.return_value = None
    graph.get_session_turns.return_value = []

    return graph


@pytest.fixture
def engine(mock_llm, mock_graph):
    return QueryEngine(mock_llm, mock_graph)


# ------------------------------------------------------------------
# Test 1: Intent classification is used (not concept extraction)
# ------------------------------------------------------------------

def test_query_uses_intent_classification(engine, mock_llm, mock_graph):
    """classify_intent is called instead of the old concept extraction approach."""
    result = engine.query("What is Apple's revenue?")
    mock_llm.classify_intent.assert_called_once_with("What is Apple's revenue?")
    # The old extract_json for concept extraction should NOT be called
    mock_llm.extract_json.assert_not_called()
    assert isinstance(result, QueryResult)


# ------------------------------------------------------------------
# Test 2: LOOKUP intent calls traverse_entity_neighborhood
# ------------------------------------------------------------------

def test_query_lookup_uses_neighborhood(engine, mock_llm, mock_graph):
    """LOOKUP intent should call traverse_entity_neighborhood for each resolved entity."""
    mock_llm.classify_intent.return_value = (QueryIntent.LOOKUP, ["Apple"])
    result = engine.query("What is Apple?")
    mock_graph.traverse_entity_neighborhood.assert_called_with(1)
    assert result.answer == "Apple's revenue was $100B."


# ------------------------------------------------------------------
# Test 3: RELATIONSHIP intent calls find_entity_paths
# ------------------------------------------------------------------

def test_query_relationship_uses_path_finding(engine, mock_llm, mock_graph):
    """RELATIONSHIP intent should call find_entity_paths between entity pairs."""
    mock_llm.classify_intent.return_value = (QueryIntent.RELATIONSHIP, ["Apple", "Revenue"])
    result = engine.query("How does Apple relate to Revenue?")
    mock_graph.find_entity_paths.assert_called_once_with("Apple", "Revenue")
    # Also calls neighborhood for each entity
    assert mock_graph.traverse_entity_neighborhood.call_count == 2


# ------------------------------------------------------------------
# Test 4: EXPLORATION intent calls get_multi_hop_entities
# ------------------------------------------------------------------

def test_query_exploration_uses_multi_hop(engine, mock_llm, mock_graph):
    """EXPLORATION intent should call get_multi_hop_entities for broader reach."""
    mock_llm.classify_intent.return_value = (QueryIntent.EXPLORATION, ["Apple"])
    result = engine.query("Tell me about Apple's ecosystem")
    mock_graph.traverse_entity_neighborhood.assert_called_with(1)
    mock_graph.get_multi_hop_entities.assert_called_with(1)


# ------------------------------------------------------------------
# Test 5: Returns QueryResult dataclass (not dict)
# ------------------------------------------------------------------

def test_query_returns_query_result_dataclass(engine, mock_llm, mock_graph):
    """query() must return a QueryResult dataclass, not a plain dict."""
    result = engine.query("What is Apple?")
    assert isinstance(result, QueryResult)
    assert isinstance(result.answer, str)
    assert isinstance(result.sources, list)
    assert isinstance(result.concepts, list)
    assert isinstance(result.related_entities, list)
    assert isinstance(result.graph_queries, list)
    assert isinstance(result.traversal_path, list)


# ------------------------------------------------------------------
# Test 6: graph_queries is populated
# ------------------------------------------------------------------

def test_query_returns_graph_queries(engine, mock_llm, mock_graph):
    """QueryResult.graph_queries should contain GraphQuery objects from traversal."""
    result = engine.query("What is Apple?")
    assert len(result.graph_queries) > 0
    assert all(isinstance(gq, GraphQuery) for gq in result.graph_queries)
    assert result.graph_queries[0].purpose == "neighborhood"


# ------------------------------------------------------------------
# Test 7: traversal_path has steps
# ------------------------------------------------------------------

def test_query_returns_traversal_path(engine, mock_llm, mock_graph):
    """QueryResult.traversal_path should have TraversalStep objects."""
    result = engine.query("What is Apple?")
    assert len(result.traversal_path) > 0
    assert all(isinstance(ts, TraversalStep) for ts in result.traversal_path)
    step = result.traversal_path[0]
    assert step.step_number == 1
    assert step.node_type == "section"
    assert step.node_id == 1


# ------------------------------------------------------------------
# Test 8: session_id passthrough
# ------------------------------------------------------------------

def test_query_session_id_passthrough(engine, mock_llm, mock_graph):
    """session_id should appear in the result unchanged."""
    result = engine.query("What is Apple?", session_id=42)
    assert result.session_id == 42


def test_query_session_id_auto_created(engine, mock_llm, mock_graph):
    """session_id is auto-created when not provided (no longer None)."""
    result = engine.query("What is Apple?")
    assert result.session_id == 1  # create_session returns 1 by default
    mock_graph.create_session.assert_called_once()


# ------------------------------------------------------------------
# Test 9: Fallback when no entities resolved
# ------------------------------------------------------------------

def test_query_fallback_on_no_entities(engine, mock_llm, mock_graph):
    """When classify_intent returns no entities, return early with a message."""
    mock_llm.classify_intent.return_value = (QueryIntent.LOOKUP, [])
    result = engine.query("hmm")
    assert "could not extract" in result.answer.lower()
    assert result.concepts == []


def test_query_fallback_title_search_when_traversal_empty(engine, mock_llm, mock_graph):
    """When graph traversal returns nothing, fall back to title substring search."""
    mock_graph.get_all_entities.return_value = [
        {"entity_id": 1, "name": "Apple", "entity_type": "ORGANIZATION", "description": ""},
    ]
    # Make traversal return nothing
    mock_graph.traverse_entity_neighborhood.return_value = {
        "sections": [], "entities": [], "graph_query": _make_graph_query(),
    }
    mock_graph.get_entity_sections.return_value = []
    # Title search finds something
    mock_graph.get_all_documents.return_value = [{"doc_id": 1, "doc_name": "report.pdf"}]
    mock_graph.get_document_sections.return_value = [
        {"section_id": 5, "title": "Apple Revenue", "text_content": "data",
         "depth_level": 0, "start_index": 1},
    ]
    result = engine.query("What is Apple?")
    assert len(result.sources) > 0
    mock_graph.get_all_documents.assert_called()


# ------------------------------------------------------------------
# Test 10: Long questions get truncated
# ------------------------------------------------------------------

def test_query_truncates_long_questions(engine, mock_llm, mock_graph):
    """Questions over MAX_QUERY_LENGTH chars should be truncated, not crash."""
    long_q = "x" * 10_000
    result = engine.query(long_q)
    # classify_intent receives the truncated question
    called_q = mock_llm.classify_intent.call_args[0][0]
    assert len(called_q) == MAX_QUERY_LENGTH


# ------------------------------------------------------------------
# Test 11: _build_context respects token budget
# ------------------------------------------------------------------

def test_build_context_token_budget(engine):
    """Context should stay within the token budget, truncating if needed."""
    sections = [
        {"title": f"Section {i}", "text_content": "x" * 5000, "doc_name": "test.pdf",
         "depth_level": 0, "relevance": "MENTIONS"}
        for i in range(20)
    ]
    context = engine._build_context(sections, [])
    # 20 sections * 5000 chars = 100k chars. Should be much less than that.
    assert len(context) < 100_000


# ------------------------------------------------------------------
# Test 12: _reason handles OllamaError
# ------------------------------------------------------------------

def test_reason_handles_ollama_error(engine, mock_llm):
    """_reason should return an error message when the LLM fails."""
    mock_llm.chat.side_effect = OllamaError("failed")
    result = engine._reason("question", "context")
    assert "error" in result.lower()


# ------------------------------------------------------------------
# Test 13: COMPARISON intent uses separate neighborhoods
# ------------------------------------------------------------------

def test_query_comparison_uses_neighborhood_per_entity(engine, mock_llm, mock_graph):
    """COMPARISON intent should call traverse_entity_neighborhood once per entity."""
    mock_llm.classify_intent.return_value = (QueryIntent.COMPARISON, ["Apple", "Revenue"])
    result = engine.query("Compare Apple and Revenue")
    assert mock_graph.traverse_entity_neighborhood.call_count == 2
    calls = mock_graph.traverse_entity_neighborhood.call_args_list
    assert calls[0] == call(1)
    assert calls[1] == call(2)


# ------------------------------------------------------------------
# Test 14: HIERARCHICAL intent uses section descendants
# ------------------------------------------------------------------

def test_query_hierarchical_uses_descendants(engine, mock_llm, mock_graph):
    """HIERARCHICAL intent should call traverse_section_descendants."""
    mock_llm.classify_intent.return_value = (QueryIntent.HIERARCHICAL, ["Apple"])
    mock_graph.get_entity_sections.return_value = [
        {"section_id": 1, "title": "Apple Section", "text_content": "data",
         "depth_level": 0, "doc_name": "report.pdf"},
    ]
    result = engine.query("Show details about Apple section")
    mock_graph.traverse_section_descendants.assert_called_with(1)


# ------------------------------------------------------------------
# Test 15: Entity resolution works by substring match
# ------------------------------------------------------------------

def test_resolve_entity_ids(engine, mock_graph):
    """_resolve_entity_ids should match by case-insensitive substring."""
    mock_graph.get_all_entities.return_value = [
        {"entity_id": 1, "name": "Apple Inc.", "entity_type": "ORGANIZATION"},
        {"entity_id": 2, "name": "Google LLC", "entity_type": "ORGANIZATION"},
    ]
    resolved = engine._resolve_entity_ids(["apple", "Google"])
    assert len(resolved) == 2
    assert resolved[0]["entity_id"] == 1
    assert resolved[1]["entity_id"] == 2


def test_resolve_entity_ids_no_match(engine, mock_graph):
    """_resolve_entity_ids returns empty list when nothing matches."""
    mock_graph.get_all_entities.return_value = [
        {"entity_id": 1, "name": "Apple", "entity_type": "ORGANIZATION"},
    ]
    resolved = engine._resolve_entity_ids(["Nonexistent"])
    assert resolved == []


# ------------------------------------------------------------------
# Test 16: No relevant info returns proper QueryResult
# ------------------------------------------------------------------

def test_query_no_matches_returns_message(engine, mock_llm, mock_graph):
    """When nothing is found at all, return a helpful message."""
    mock_graph.get_all_entities.return_value = []
    mock_graph.get_entity_sections.return_value = []
    mock_graph.get_all_documents.return_value = []
    mock_llm.classify_intent.return_value = (QueryIntent.LOOKUP, ["nonexistent"])
    result = engine.query("nonexistent concept")
    assert isinstance(result, QueryResult)
    assert "no relevant information" in result.answer.lower()


# ------------------------------------------------------------------
# Session integration tests (Task 10)
# ------------------------------------------------------------------


def test_query_creates_session_automatically(mock_llm, mock_graph):
    """First query without session_id creates a new session."""
    mock_graph.create_session.return_value = 1
    mock_graph.create_turn.return_value = 10
    engine = QueryEngine(mock_llm, mock_graph)

    result = engine.query("What is Apple?")

    mock_graph.create_session.assert_called_once_with(title="What is Apple?")
    mock_graph.create_turn.assert_called_once()
    assert result.session_id == 1


def test_query_uses_existing_session(mock_llm, mock_graph):
    """Query with session_id loads context from previous turns."""
    mock_graph.get_session_context.return_value = {
        "primary_entities": ["Revenue"],
    }
    mock_graph.get_session_turns.return_value = [
        {"turn_id": 1, "turn_number": 1, "question": "prev"},
    ]
    mock_graph.create_turn.return_value = 20
    engine = QueryEngine(mock_llm, mock_graph)

    result = engine.query("What is Apple?", session_id=42)

    mock_graph.get_session_context.assert_called_once_with(42)
    mock_graph.get_session_turns.assert_called_once_with(42)
    assert result.session_id == 42
    # Turn should be number 2 (one existing turn + 1)
    call_args = mock_graph.create_turn.call_args
    assert call_args[0][1] == 2  # turn_number


def test_query_records_turn_entities(mock_llm, mock_graph):
    """Query records touched entities via insert_turn_entity."""
    mock_graph.create_session.return_value = 1
    mock_graph.create_turn.return_value = 10
    engine = QueryEngine(mock_llm, mock_graph)

    engine.query("What is Apple?")

    # Should have been called for primary (entity_id=1) and referenced (entity_id=2)
    assert mock_graph.insert_turn_entity.call_count >= 1
    # Check the first call was PRIMARY for entity 1
    first_call = mock_graph.insert_turn_entity.call_args_list[0]
    assert first_call[0][0] == 10  # turn_id
    assert first_call[0][1] == 1   # entity_id
    assert first_call[0][2] == "PRIMARY"


def test_query_records_turn_sections(mock_llm, mock_graph):
    """Query records used sections via insert_turn_section."""
    mock_graph.create_session.return_value = 1
    mock_graph.create_turn.return_value = 10
    engine = QueryEngine(mock_llm, mock_graph)

    engine.query("What is Apple?")

    mock_graph.insert_turn_section.assert_called()
    first_call = mock_graph.insert_turn_section.call_args_list[0]
    assert first_call[0][0] == 10  # turn_id
    assert first_call[0][1] == 1   # section_id
    assert first_call[1]["rank_score"] == 1.0


def test_query_updates_turn_answer(mock_llm, mock_graph):
    """Query stores the LLM answer back into the turn record."""
    mock_graph.create_session.return_value = 1
    mock_graph.create_turn.return_value = 10
    engine = QueryEngine(mock_llm, mock_graph)

    engine.query("What is Apple?")

    mock_graph.update_turn_answer.assert_called_once_with(10, "Apple's revenue was $100B.")


def test_query_session_graceful_degradation(mock_llm, mock_graph):
    """Session operations failing should not break the query itself."""
    mock_graph.create_session.side_effect = Exception("DB unavailable")
    engine = QueryEngine(mock_llm, mock_graph)

    # Should still return a valid result
    result = engine.query("What is Apple?")
    assert isinstance(result, QueryResult)
    assert result.answer == "Apple's revenue was $100B."


def test_query_existing_session_injects_previous_entities(mock_llm, mock_graph):
    """Previous turn entities supplement the current entity resolution."""
    # Set up: session context has "Google" from a previous turn
    mock_graph.get_session_context.return_value = {
        "primary_entities": ["Google"],
    }
    mock_graph.get_session_turns.return_value = [{"turn_id": 1, "turn_number": 1}]
    mock_graph.create_turn.return_value = 20
    # Add Google to the entity list so it can be resolved
    mock_graph.get_all_entities.return_value = [
        {"entity_id": 1, "name": "Apple", "entity_type": "ORGANIZATION", "description": "Tech company"},
        {"entity_id": 2, "name": "Revenue", "entity_type": "METRIC", "description": "Income"},
        {"entity_id": 3, "name": "Google", "entity_type": "ORGANIZATION", "description": "Search"},
    ]
    engine = QueryEngine(mock_llm, mock_graph)

    # Query only mentions Apple, but Google should be pulled in from session context
    result = engine.query("What is Apple?", session_id=42)

    # traverse_entity_neighborhood should be called for Apple (1) AND Google (3)
    neighborhood_calls = mock_graph.traverse_entity_neighborhood.call_args_list
    entity_ids_traversed = [c[0][0] for c in neighborhood_calls]
    assert 1 in entity_ids_traversed  # Apple
    assert 3 in entity_ids_traversed  # Google from session context
