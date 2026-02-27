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
