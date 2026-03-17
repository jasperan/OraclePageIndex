"""Tests for the graph enrichment agent."""
from unittest.mock import MagicMock
from oracle_pageindex.enricher import GraphEnricher


def _make_enricher():
    mock_llm = MagicMock()
    mock_graph = MagicMock()
    return GraphEnricher(mock_llm, mock_graph), mock_llm, mock_graph


def test_detect_isolated_entities():
    enricher, _, graph = _make_enricher()
    graph.get_isolated_entities.return_value = [
        {"entity_id": 1, "name": "Tim Cook", "entity_type": "PERSON", "mention_count": 5}
    ]
    isolated = enricher.detect_isolated_entities()
    assert len(isolated) == 1
    assert isolated[0]["mention_count"] == 5


def test_detect_cooccurring_pairs():
    enricher, _, graph = _make_enricher()
    graph.get_cooccurring_pairs.return_value = [
        {"entity1_name": "Tim Cook", "entity2_name": "Apple Inc.",
         "entity1_id": 1, "entity2_id": 2, "shared_sections": 4}
    ]
    pairs = enricher.detect_cooccurring_pairs()
    assert len(pairs) == 1
    assert pairs[0]["shared_sections"] == 4


def test_enrich_pair_calls_llm():
    enricher, llm, graph = _make_enricher()
    graph.get_shared_section_text.return_value = "Tim Cook is CEO of Apple Inc."
    llm.chat.return_value = "LEADS"
    result = enricher.enrich_pair(
        {"entity1_id": 1, "entity1_name": "Tim Cook", "entity1_type": "PERSON"},
        {"entity2_id": 2, "entity2_name": "Apple Inc.", "entity2_type": "ORGANIZATION"},
    )
    assert result["relationship"] == "LEADS"


def test_enrich_pair_returns_none():
    enricher, llm, graph = _make_enricher()
    graph.get_shared_section_text.return_value = "Some text"
    llm.chat.return_value = "NONE"
    result = enricher.enrich_pair(
        {"entity1_id": 1, "entity1_name": "A", "entity1_type": "CONCEPT"},
        {"entity2_id": 2, "entity2_name": "B", "entity2_type": "CONCEPT"},
    )
    assert result is None


def test_enrich_inserts_with_provenance():
    enricher, llm, graph = _make_enricher()
    graph.get_cooccurring_pairs.return_value = [
        {"entity1_name": "Tim Cook", "entity2_name": "Apple",
         "entity1_id": 1, "entity2_id": 2,
         "entity1_type": "PERSON", "entity2_type": "ORG",
         "shared_sections": 3}
    ]
    graph.get_shared_section_text.return_value = "CEO of Apple"
    llm.chat.return_value = "LEADS"
    stats = enricher.enrich(max_candidates=10)
    graph.insert_enriched_relationship.assert_called_once()
    assert stats["new_relationships"] == 1


def test_enrich_dry_run():
    enricher, llm, graph = _make_enricher()
    graph.get_cooccurring_pairs.return_value = [
        {"entity1_name": "A", "entity2_name": "B",
         "entity1_id": 1, "entity2_id": 2,
         "entity1_type": "C", "entity2_type": "D",
         "shared_sections": 2}
    ]
    graph.get_shared_section_text.return_value = "text"
    llm.chat.return_value = "RELATED_TO"
    stats = enricher.enrich(max_candidates=10, dry_run=True)
    graph.insert_enriched_relationship.assert_not_called()
    assert stats["new_relationships"] == 1


def test_enrich_max_candidates():
    enricher, llm, graph = _make_enricher()
    graph.get_cooccurring_pairs.return_value = [
        {"entity1_name": f"E{i}", "entity2_name": f"F{i}",
         "entity1_id": i, "entity2_id": i + 100,
         "entity1_type": "C", "entity2_type": "C",
         "shared_sections": 2}
        for i in range(20)
    ]
    graph.get_shared_section_text.return_value = "text"
    llm.chat.return_value = "RELATED_TO"
    stats = enricher.enrich(max_candidates=5)
    assert llm.chat.call_count == 5
    assert stats["candidates_analyzed"] == 5
