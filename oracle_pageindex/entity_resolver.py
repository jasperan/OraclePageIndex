"""Vector-assisted entity resolution using Oracle VECTOR_DISTANCE."""
import logging

logger = logging.getLogger(__name__)


class EntityResolver:
    """Resolves duplicate entities using embedding similarity + LLM confirmation.

    Uses Oracle VECTOR columns for fuzzy matching entity names, with LLM
    confirmation for ambiguous cases. Vectors serve disambiguation only, not retrieval.
    """

    CONFIRM_PROMPT = (
        "Are these the same real-world entity?\n"
        "Entity A: '{name_a}' ({type_a})\n"
        "Entity B: '{name_b}' ({type_b})\n"
        "Answer YES or NO only."
    )

    def __init__(self, llm, graph_store, config):
        self.llm = llm
        self.graph = graph_store
        self.enabled = config.get("enabled", False) if config else False
        self.embedding_model = (
            config.get("embedding_model", "nomic-embed-text") if config else "nomic-embed-text"
        )
        self.similarity_threshold = config.get("similarity_threshold", 0.3) if config else 0.3
        self.auto_confirm_threshold = (
            config.get("auto_confirm_threshold", 0.15) if config else 0.15
        )

    def find_candidates(self, entity_id, name, entity_type):
        """Find similar entities using vector distance on name embeddings."""
        if not self.enabled:
            return []

        embedding = self.llm.embed(name, model=self.embedding_model)
        if not embedding:
            return []

        return self.graph.find_similar_entities(
            embedding, entity_type, self.similarity_threshold, exclude_id=entity_id
        )

    def should_confirm(self, distance):
        """Determine confirmation strategy based on distance.

        Returns: 'auto' (close match), 'llm' (ambiguous), or 'reject' (too far)
        """
        if distance < self.auto_confirm_threshold:
            return "auto"
        elif distance < self.similarity_threshold:
            return "llm"
        else:
            return "reject"

    def llm_confirm(self, entity_a, entity_b):
        """Ask LLM to confirm whether two entities are the same."""
        prompt = self.CONFIRM_PROMPT.format(
            name_a=entity_a["name"],
            type_a=entity_a.get("entity_type", ""),
            name_b=entity_b["name"],
            type_b=entity_b.get("entity_type", ""),
        )
        try:
            response = self.llm.chat(prompt, max_retries=2)
            return "YES" in response.upper()
        except Exception:
            return False

    def resolve_entity(self, entity_id, name, entity_type):
        """Resolve a single entity against existing entities.

        Returns list of confirmed aliases.
        """
        if not self.enabled:
            return []

        candidates = self.find_candidates(entity_id, name, entity_type)
        aliases = []

        for candidate in candidates:
            distance = candidate.get("distance", 1.0)
            action = self.should_confirm(distance)

            if action == "reject":
                continue
            elif action == "auto":
                confirmed = True
            else:  # "llm"
                confirmed = self.llm_confirm(
                    {"name": name, "entity_type": entity_type},
                    candidate,
                )

            if confirmed:
                # The existing entity (candidate) becomes canonical
                canonical_id = candidate["entity_id"]
                self.graph.insert_entity_alias(
                    canonical_id=canonical_id,
                    alias_id=entity_id,
                    similarity=1.0 - distance,
                    confirmed=1 if action == "llm" else 0,
                )
                self.graph.update_entity_canonical(entity_id, canonical_id)
                aliases.append(candidate)
                break  # One canonical match is enough

        return aliases

    def resolve_all_new_entities(self, entity_ids):
        """Batch resolution for a list of newly created entity IDs.

        Returns dict with resolution stats.
        """
        if not self.enabled:
            return {"resolved": 0, "total": len(entity_ids)}

        resolved_count = 0
        all_entities = self.graph.get_all_entities()
        entity_map = {e["entity_id"]: e for e in all_entities}

        for eid in entity_ids:
            entity = entity_map.get(eid)
            if not entity:
                continue
            aliases = self.resolve_entity(eid, entity["name"], entity.get("entity_type", ""))
            if aliases:
                resolved_count += 1

        return {"resolved": resolved_count, "total": len(entity_ids)}
