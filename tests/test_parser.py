import pytest
from unittest.mock import MagicMock, patch

from oracle_pageindex.parser import DocumentParser


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.model = "llama3.1"
    return llm


@pytest.fixture
def parser(mock_llm):
    return DocumentParser(llm=mock_llm)


def test_parse_pdf_file_not_found(parser):
    with pytest.raises(FileNotFoundError, match="PDF file not found"):
        parser.parse_pdf("/nonexistent/path/test.pdf")


def test_parse_pdf_not_pdf_extension(parser, tmp_path):
    txt_file = tmp_path / "test.txt"
    txt_file.write_text("not a pdf")
    with pytest.raises(ValueError, match="Expected a .pdf file"):
        parser.parse_pdf(str(txt_file))


def test_create_fallback_structure(parser):
    page_list = [("page 1 text", 10), ("page 2 text", 15)]
    result = parser._create_fallback_structure(page_list)
    assert len(result) == 2
    assert result[0]["title"] == "Page 1"
    assert result[0]["physical_index"] == 1
    assert result[1]["title"] == "Page 2"
    assert result[1]["physical_index"] == 2


def test_generate_tree_from_pages_returns_none_on_llm_error(parser, mock_llm):
    from oracle_pageindex.llm import OllamaError
    mock_llm.chat.side_effect = OllamaError("failed")
    page_list = [("page text", 100)]
    result = parser.generate_tree_from_pages(page_list, "test.pdf")
    assert result is None


def test_generate_tree_from_pages_parses_response(parser, mock_llm):
    mock_llm.chat.return_value = '```json\n[{"structure": "1", "title": "Intro", "physical_index": 1}]\n```'
    mock_llm.extract_json.return_value = [
        {"structure": "1", "title": "Intro", "physical_index": 1}
    ]
    page_list = [("page text", 100)]
    result = parser.generate_tree_from_pages(page_list, "test.pdf")
    assert result is not None
    assert len(result) == 1
    assert result[0]["title"] == "Intro"


def test_generate_summaries_batches_nodes(mock_llm):
    parser = DocumentParser(llm=mock_llm, summary_batch_size=2, summary_workers=1)
    mock_llm.chat.return_value = "[]"
    mock_llm.extract_json.return_value = [
        {"index": 0, "summary": "First summary"},
        {"index": 1, "summary": "Second summary"},
    ]
    structure = [
        {"title": "First", "text": "First text"},
        {"title": "Second", "text": "Second text"},
    ]

    parser._generate_summaries(structure)

    assert mock_llm.chat.call_count == 1
    assert structure[0]["summary"] == "First summary"
    assert structure[1]["summary"] == "Second summary"
