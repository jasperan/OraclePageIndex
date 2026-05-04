import asyncio

import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock, patch

from oracle_pageindex.indexer import Indexer, _lookup_entity_id


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.model = "llama3.1"
    return llm


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute_returning.return_value = 1
    db.fetchall.return_value = []
    db.fetchone.return_value = None
    return db


@pytest.fixture
def opt():
    return SimpleNamespace(
        toc_check_page_num=5,
        max_token_num_each_node=20000,
        pdf_parser="PyMuPDF",
        if_add_node_id="yes",
        if_add_node_summary="no",
        if_extract_entities="no",
    )


@pytest.fixture
def indexer(mock_llm, mock_db, opt):
    return Indexer(mock_llm, mock_db, opt)


def test_indexer_init(indexer):
    assert indexer.parser is not None
    assert indexer.graph is not None
    assert indexer.extractor is not None
    assert indexer.extract_entities is False  # disabled in opt


def test_insert_tree_nodes_list(indexer, mock_db):
    mock_db.execute_returning.return_value = 1
    tree = [
        {"title": "Section 1", "node_id": "0001", "summary": "", "text": "content",
         "start_index": 1, "end_index": 3},
    ]
    all_sections = []
    indexer._insert_tree_nodes(tree, doc_id=1, parent_section_id=None,
                                depth=0, all_sections=all_sections)
    assert len(all_sections) == 1
    assert all_sections[0]["title"] == "Section 1"


def test_insert_tree_nodes_nested(indexer, mock_db):
    call_count = [0]

    def mock_returning(*args, **kwargs):
        call_count[0] += 1
        return call_count[0]

    mock_db.execute_returning.side_effect = mock_returning

    tree = {
        "title": "Parent", "node_id": "0001", "summary": "", "text": "parent text",
        "start_index": 1, "end_index": 5,
        "nodes": [
            {"title": "Child", "node_id": "0002", "summary": "", "text": "child text",
             "start_index": 2, "end_index": 3},
        ],
    }
    all_sections = []
    indexer._insert_tree_nodes(tree, doc_id=1, parent_section_id=None,
                                depth=0, all_sections=all_sections)
    assert len(all_sections) == 2
    # Hierarchy edge should have been created for the child
    mock_db.execute.assert_called_once()


@patch("oracle_pageindex.indexer.Indexer._insert_tree_nodes")
def test_index_pdf_calls_pipeline(mock_insert, indexer, mock_db):
    mock_insert.return_value = None
    mock_db.execute_returning.return_value = 1

    with patch.object(indexer.parser, "build_tree", return_value={
        "doc_name": "test.pdf",
        "structure": [],
        "page_list": [("page text", 100)],
    }):
        stats = indexer.index_pdf("/path/to/test.pdf")

    assert stats["doc_name"] == "test.pdf"
    assert stats["doc_id"] == 1
    assert stats["entities"] == 0  # extraction disabled


# -------------------------------------------------------------------
# Entity resolution wiring
# -------------------------------------------------------------------


@pytest.fixture
def opt_with_resolution():
    return SimpleNamespace(
        toc_check_page_num=5,
        max_token_num_each_node=20000,
        pdf_parser="PyMuPDF",
        if_add_node_id="yes",
        if_add_node_summary="no",
        if_extract_entities="yes",
        entity_resolution={
            "enabled": True,
            "embedding_model": "nomic-embed-text",
            "similarity_threshold": 0.3,
            "auto_confirm_threshold": 0.15,
        },
    )


def test_indexer_init_with_resolver(mock_llm, mock_db, opt_with_resolution):
    """EntityResolver is created when entity_resolution config is present."""
    idx = Indexer(mock_llm, mock_db, opt_with_resolution)
    assert idx.resolver is not None


def test_indexer_init_without_resolver(mock_llm, mock_db, opt):
    """Resolver is None when entity_resolution config is absent."""
    idx = Indexer(mock_llm, mock_db, opt)
    assert idx.resolver is None


@patch("oracle_pageindex.indexer.EntityExtractor")
@patch("oracle_pageindex.indexer.EntityResolver")
def test_index_pdf_runs_entity_resolution(MockResolver, MockExtractor, mock_llm, mock_db, opt_with_resolution):
    """Indexing pipeline calls entity resolver after extraction."""
    # Set up mock extractor (async methods)
    mock_extractor_inst = MagicMock()
    mock_extractor_inst.extract_entities_for_sections = AsyncMock(return_value=None)
    mock_extractor_inst.extract_relationships = AsyncMock(return_value=[])
    MockExtractor.return_value = mock_extractor_inst

    # Set up mock resolver
    mock_resolver_inst = MagicMock()
    mock_resolver_inst.resolve_all_new_entities.return_value = {"resolved": 1, "total": 2}
    MockResolver.return_value = mock_resolver_inst

    # IDs returned from execute_returning: doc_id=1, section_id=2, entity_id=3
    call_count = [0]

    def mock_returning(*args, **kwargs):
        call_count[0] += 1
        return call_count[0]

    mock_db.execute_returning.side_effect = mock_returning

    idx = Indexer(mock_llm, mock_db, opt_with_resolution)

    # Patch parser to return a simple tree with one section
    with patch.object(idx.parser, "build_tree", return_value={
        "doc_name": "test.pdf",
        "structure": [{"title": "Sec1", "node_id": "0001", "summary": "s",
                        "text": "content", "start_index": 1, "end_index": 2}],
        "page_list": [("page text", 100)],
    }):
        # Patch extract_entities_for_sections to inject entities into sections
        async def fake_extract(sections):
            for sec in sections:
                sec["_entities"] = [
                    {"name": "Acme Corp", "type": "ORGANIZATION", "relevance": "DISCUSSES"},
                    {"name": "WidgetX", "type": "TECHNOLOGY", "relevance": "MENTIONS"},
                ]

        mock_extractor_inst.extract_entities_for_sections.side_effect = fake_extract

        stats = idx.index_pdf("/path/to/test.pdf")

    # Resolver should have been called with the entity IDs
    mock_resolver_inst.resolve_all_new_entities.assert_called_once()
    called_ids = mock_resolver_inst.resolve_all_new_entities.call_args[0][0]
    assert len(called_ids) == 2  # two unique entities


@patch("oracle_pageindex.indexer.EntityExtractor")
def test_index_pdf_stores_relationships_with_typed_endpoint_names(
    MockExtractor, mock_llm, mock_db, opt_with_resolution
):
    mock_extractor_inst = MagicMock()
    mock_extractor_inst.extract_entities_for_sections = AsyncMock(return_value=None)
    mock_extractor_inst.extract_relationships = AsyncMock(return_value=[
        {
            "source": "Acme Corp (ORGANIZATION)",
            "target": "WidgetX (TECHNOLOGY)",
            "relationship": "USES",
        }
    ])
    MockExtractor.return_value = mock_extractor_inst

    call_count = [0]

    def mock_returning(*args, **kwargs):
        call_count[0] += 1
        return call_count[0]

    mock_db.execute_returning.side_effect = mock_returning
    idx = Indexer(mock_llm, mock_db, opt_with_resolution)
    idx.resolver = None

    with patch.object(idx.parser, "build_tree", return_value={
        "doc_name": "test.pdf",
        "structure": [{"title": "Sec1", "node_id": "0001", "summary": "s",
                        "text": "content", "start_index": 1, "end_index": 2}],
        "page_list": [("page text", 100)],
    }):
        async def fake_extract(sections):
            for sec in sections:
                sec["_entities"] = [
                    {"name": "Acme Corp", "type": "ORGANIZATION", "relevance": "DISCUSSES"},
                    {"name": "WidgetX", "type": "TECHNOLOGY", "relevance": "MENTIONS"},
                ]

        mock_extractor_inst.extract_entities_for_sections.side_effect = fake_extract

        stats = idx.index_pdf("/path/to/test.pdf")

    assert stats["relationships"] == 1
    mock_db.execute.assert_called()


def test_lookup_entity_id_strips_type_suffix():
    name_to_id = {"Acme Corp": 42, "acme corp": 42}

    assert _lookup_entity_id(name_to_id, "Acme Corp (ORGANIZATION)") == 42


@patch("oracle_pageindex.indexer.EntityExtractor")
def test_index_pdf_skips_resolution_when_disabled(MockExtractor, mock_llm, mock_db, opt):
    """Resolution is skipped when resolver is None."""
    mock_extractor_inst = MagicMock()
    mock_extractor_inst.extract_entities_for_sections = AsyncMock(return_value=None)
    mock_extractor_inst.extract_relationships = AsyncMock(return_value=[])
    MockExtractor.return_value = mock_extractor_inst

    # Entity extraction is disabled in the base opt fixture
    idx = Indexer(mock_llm, mock_db, opt)
    assert idx.resolver is None

    mock_db.execute_returning.return_value = 1

    with patch.object(idx.parser, "build_tree", return_value={
        "doc_name": "test.pdf",
        "structure": [],
        "page_list": [("page text", 100)],
    }):
        with patch.object(idx, "_insert_tree_nodes"):
            stats = idx.index_pdf("/path/to/test.pdf")

    assert stats["entities"] == 0  # no entity extraction, no resolution
