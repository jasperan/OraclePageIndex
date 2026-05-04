import pytest
from unittest.mock import AsyncMock, MagicMock
from oracle_pageindex.entity_extractor import EntityExtractor


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.chat_async = AsyncMock(return_value='```json\n[{"name": "Oracle Database", "type": "TECHNOLOGY", "relevance": "DEFINES"}, {"name": "SQL", "type": "TECHNOLOGY", "relevance": "MENTIONS"}]\n```')
    llm.extract_json = MagicMock(return_value=[
        {"name": "Oracle Database", "type": "TECHNOLOGY", "relevance": "DEFINES"},
        {"name": "SQL", "type": "TECHNOLOGY", "relevance": "MENTIONS"},
    ])
    return llm


@pytest.fixture
def extractor(mock_llm):
    return EntityExtractor(mock_llm)


@pytest.mark.asyncio
async def test_extract_entities_from_text(extractor):
    entities = await extractor.extract_entities("Oracle Database uses SQL for queries.")
    assert len(entities) == 2
    assert entities[0]["name"] == "Oracle Database"
    assert entities[0]["type"] == "TECHNOLOGY"


@pytest.mark.asyncio
async def test_extract_relationships(extractor):
    extractor.llm.chat_async = AsyncMock(return_value='```json\n[{"source": "Oracle Database", "target": "SQL", "relationship": "USES"}]\n```')
    extractor.llm.extract_json = MagicMock(return_value=[
        {"source": "Oracle Database", "target": "SQL", "relationship": "USES"}
    ])
    rels = await extractor.extract_relationships(
        [{"name": "Oracle Database", "type": "TECHNOLOGY"},
         {"name": "SQL", "type": "TECHNOLOGY"}]
    )
    assert len(rels) == 1
    assert rels[0]["relationship"] == "USES"


@pytest.mark.asyncio
async def test_extract_relationships_too_few_entities(extractor):
    rels = await extractor.extract_relationships([{"name": "Only One", "type": "CONCEPT"}])
    assert rels == []


@pytest.mark.asyncio
async def test_extract_entities_respects_max_chars(mock_llm):
    extractor = EntityExtractor(mock_llm, max_chars=220)
    mock_llm.chat_async = AsyncMock(return_value="[]")
    mock_llm.extract_json.return_value = []
    text = "a" * 220 + "b" * 40

    await extractor.extract_entities(text)

    prompt = mock_llm.chat_async.call_args[0][0]
    prompt_text = prompt.split("<<", 1)[1].split(">>", 1)[0]
    assert prompt_text == "a" * 220


@pytest.mark.asyncio
async def test_extract_entities_for_sections_batches_requests(mock_llm):
    extractor = EntityExtractor(mock_llm, batch_size=2)
    mock_llm.chat_async = AsyncMock(return_value="[]")
    mock_llm.extract_json.return_value = [
        {
            "section_index": 0,
            "entities": [
                {"name": "Disney", "type": "ORGANIZATION", "relevance": "DISCUSSES"}
            ],
        },
        {
            "section_index": 1,
            "entities": [
                {"name": "ESPN", "type": "ORGANIZATION", "relevance": "MENTIONS"}
            ],
        },
    ]
    sections = [
        {"title": "A", "text": "Disney revenue increased."},
        {"title": "B", "text": "ESPN subscribers changed."},
    ]

    result = await extractor.extract_entities_for_sections(sections)

    assert mock_llm.chat_async.call_count == 1
    assert result[0]["_entities"][0]["name"] == "Disney"
    assert result[1]["_entities"][0]["name"] == "ESPN"


@pytest.mark.asyncio
async def test_extract_entities_prefers_summary_for_batch_prompt(mock_llm):
    extractor = EntityExtractor(mock_llm, batch_size=2)
    mock_llm.chat_async = AsyncMock(return_value="[]")
    mock_llm.extract_json.return_value = [
        {"section_index": 0, "entities": []},
        {"section_index": 1, "entities": []},
    ]
    sections = [
        {"title": "A", "summary": "short summary", "text": "long full text"},
        {"title": "B", "summary": "another summary", "text": "another full text"},
    ]

    await extractor.extract_entities_for_sections(sections)

    prompt = mock_llm.chat_async.call_args_list[0][0][0]
    assert "short summary" in prompt
    assert "long full text" not in prompt


@pytest.mark.asyncio
async def test_extract_entities_batch_falls_back_when_response_missing_section(mock_llm):
    extractor = EntityExtractor(mock_llm, batch_size=2)
    mock_llm.chat_async = AsyncMock(return_value="[]")
    mock_llm.extract_json.side_effect = [
        [{"section_index": 0, "entities": []}],
        [{"name": "Disney", "type": "ORGANIZATION", "relevance": "DISCUSSES"}],
        [{"name": "ESPN", "type": "ORGANIZATION", "relevance": "MENTIONS"}],
    ]
    sections = [
        {"title": "A", "text": "Disney revenue increased."},
        {"title": "B", "text": "ESPN subscribers changed."},
    ]

    result = await extractor.extract_entities_for_sections(sections)

    assert mock_llm.chat_async.call_count == 3
    assert result[0]["_entities"][0]["name"] == "Disney"
    assert result[1]["_entities"][0]["name"] == "ESPN"
