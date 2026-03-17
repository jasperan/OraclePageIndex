"""Graph enrichment agent: finds structural gaps and fills them with targeted LLM re-examination."""
import logging

logger = logging.getLogger(__name__)

# Expanded relationship types for enrichment
RELATIONSHIP_TYPES = [
    "RELATED_TO", "PART_OF", "USED_BY", "DEPENDS_ON", "COMPETES_WITH",
    "DERIVED_FROM", "LEADS", "EMPLOYED_BY", "INVESTED_IN", "REGULATES", "ACQUIRED",
]


class GraphEnricher:
    """Autonomous post-indexing pass that finds structural weaknesses in the graph
    and fills them with targeted LLM re-examination."""

    ENRICH_PROMPT = (
        "Entity A: '{name_a}' ({type_a})\n"
        "Entity B: '{name_b}' ({type_b})\n"
        "They appear together in the following text:\n\n{shared_text}\n\n"
        "What is the specific relationship between Entity A and Entity B? "
        "Choose EXACTLY ONE from: {rel_types}\n"
        "If no clear relationship exists, respond with NONE.\n"
        "Answer with ONLY the relationship type, nothing else."
    )

    def __init__(self, llm, graph_store):
        self.llm = llm
        self.graph = graph_store

    def detect_isolated_entities(self, min_mentions=2):
        """Find entities with mentions but no relationship edges."""
        return self.graph.get_isolated_entities(min_mentions)

    def detect_cooccurring_pairs(self, min_shared=2):
        """Find entity pairs that co-occur in sections but have no relationship edge."""
        return self.graph.get_cooccurring_pairs(min_shared)

    def enrich_pair(self, entity1, entity2):
        """Use LLM to determine the relationship between a co-occurring entity pair.

        Returns dict with relationship info, or None if no relationship found.
        """
        shared_text = self.graph.get_shared_section_text(
            entity1["entity1_id"] if "entity1_id" in entity1 else entity1["entity_id"],
            entity2["entity2_id"] if "entity2_id" in entity2 else entity2["entity_id"],
        )
        if not shared_text:
            return None

        prompt = self.ENRICH_PROMPT.format(
            name_a=entity1.get("entity1_name", entity1.get("name", "")),
            type_a=entity1.get("entity1_type", entity1.get("entity_type", "")),
            name_b=entity2.get("entity2_name", entity2.get("name", "")),
            type_b=entity2.get("entity2_type", entity2.get("entity_type", "")),
            shared_text=shared_text[:2000],
            rel_types=", ".join(RELATIONSHIP_TYPES),
        )

        try:
            response = self.llm.chat(prompt, max_retries=2).strip().upper()
        except Exception:
            return None

        # Clean up response
        for rel_type in RELATIONSHIP_TYPES:
            if rel_type in response:
                return {"relationship": rel_type}

        if "NONE" in response:
            return None

        return None

    def enrich(self, max_candidates=50, dry_run=False, doc_id=None):
        """Run the full enrichment pipeline.

        Args:
            max_candidates: Maximum co-occurring pairs to examine.
            dry_run: If True, detect but don't insert edges.
            doc_id: If set, only examine pairs from this document.

        Returns:
            Stats dict with counts.
        """
        pairs = self.detect_cooccurring_pairs()
        pairs = pairs[:max_candidates]

        stats = {
            "candidates_analyzed": 0,
            "new_relationships": 0,
            "relationship_types": {},
            "llm_calls": 0,
        }

        for pair in pairs:
            stats["candidates_analyzed"] += 1
            stats["llm_calls"] += 1

            result = self.enrich_pair(pair, pair)
            if result is None:
                continue

            rel_type = result["relationship"]
            stats["new_relationships"] += 1
            stats["relationship_types"][rel_type] = stats["relationship_types"].get(rel_type, 0) + 1

            if not dry_run:
                source_id = pair.get("entity1_id")
                target_id = pair.get("entity2_id")
                self.graph.insert_enriched_relationship(
                    source_id=source_id,
                    target_id=target_id,
                    relationship=rel_type,
                    confidence=0.8,
                )

        return stats
