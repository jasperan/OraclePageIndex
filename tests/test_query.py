import pytest
from unittest.mock import MagicMock

from oracle_pageindex.llm import OllamaError
from oracle_pageindex.query import QueryEngine


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.chat.return_value = '["Apple", "revenue"]'
    llm.extract_json.return_value = ["Apple", "revenue"]
    return llm


@pytest.fixture
def mock_graph():
    graph = MagicMock()
    graph.get_entity_sections.return_value = []
    graph.get_related_entities.return_value = []
    graph.get_all_documents.return_value = []
    return graph


@pytest.fixture
def engine(mock_llm, mock_graph):
    return QueryEngine(mock_llm, mock_graph)


def test_query_extracts_concepts(engine, mock_llm, mock_graph):
    mock_graph.get_entity_sections.return_value = [
        {"section_id": 1, "title": "Revenue", "summary": "Q1 results",
         "text_content": "Apple revenue...", "depth_level": 0,
         "relevance": "DEFINES", "start_index": 1, "doc_id": 1,
         "doc_name": "10K.pdf"},
    ]
    mock_llm.chat.side_effect = [
        '["Apple", "revenue"]',  # concept extraction
        "Apple's revenue was $100B.",  # reasoning
    ]
    mock_llm.extract_json.return_value = ["Apple", "revenue"]

    result = engine.query("What is Apple's revenue?")
    assert result["concepts"] == ["Apple", "revenue"]
    assert "answer" in result


def test_query_no_concepts(engine, mock_llm):
    mock_llm.chat.side_effect = OllamaError("failed")
    result = engine.query("test")
    assert "could not extract" in result["answer"].lower()


def test_query_no_matches_returns_message(engine, mock_llm, mock_graph):
    mock_graph.get_entity_sections.return_value = []
    mock_graph.get_all_documents.return_value = []
    result = engine.query("nonexistent concept")
    assert "no relevant information" in result["answer"].lower()


def test_query_truncates_long_question(engine, mock_llm, mock_graph):
    long_q = "x" * 10_000
    mock_graph.get_entity_sections.return_value = []
    mock_graph.get_all_documents.return_value = []
    result = engine.query(long_q)
    # Should not crash, question gets truncated internally
    assert isinstance(result, dict)


def test_fallback_title_search(engine, mock_llm, mock_graph):
    mock_graph.get_entity_sections.return_value = []
    mock_graph.get_all_documents.return_value = [
        {"doc_id": 1, "doc_name": "test.pdf"},
    ]
    mock_graph.get_document_sections.return_value = [
        {"section_id": 1, "title": "Apple Revenue Section", "summary": "revenue data",
         "text_content": "Apple made $100B", "depth_level": 0,
         "start_index": 1},
    ]
    mock_llm.chat.side_effect = [
        '["Apple"]',  # concept extraction
        "Apple's revenue was...",  # reasoning
    ]
    mock_llm.extract_json.return_value = ["Apple"]

    result = engine.query("What about Apple?")
    assert len(result["sources"]) > 0


def test_build_context_respects_token_budget(engine):
    sections = [
        {"title": f"Section {i}", "text_content": "x" * 5000, "doc_name": "test.pdf",
         "depth_level": 0, "relevance": "MENTIONS"}
        for i in range(20)
    ]
    context = engine._build_context(sections, [])
    # Should be truncated, not all 20 sections included
    assert len(context) < len("x") * 5000 * 20


def test_reason_handles_ollama_error(engine, mock_llm):
    mock_llm.chat.side_effect = OllamaError("failed")
    result = engine._reason("question", "context")
    assert "error" in result.lower()
