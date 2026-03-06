import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from oracle_pageindex.indexer import Indexer


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
