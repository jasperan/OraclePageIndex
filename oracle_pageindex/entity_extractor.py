import json
import logging

logger = logging.getLogger(__name__)


class EntityExtractor:
    def __init__(self, llm, batch_size=1, max_chars=4000):
        self.llm = llm
        self.batch_size = max(1, int(batch_size or 1))
        self.max_chars = max(200, int(max_chars or 4000))

    async def extract_entities(self, text: str) -> list[dict]:
        """Extract named entities and concepts from text using Ollama."""
        prompt = f"""Extract key entities and concepts from this text. For each entity, provide:
- name: the entity name (use the most complete/formal form, e.g. "Apple Inc." not "Apple")
- type: one of PERSON, ORGANIZATION, TECHNOLOGY, CONCEPT, LOCATION, EVENT, METRIC
- relevance: one of DEFINES (text defines this entity), DISCUSSES (text discusses it in depth), MENTIONS (brief reference)

Only include entities you are confident about. Deduplicate: if the same entity appears with different names (e.g. "ML" and "Machine Learning"), use the most formal name.

Text:
<<{text[:self.max_chars]}>>

Return a JSON array of objects. Return ONLY the JSON array wrapped in ```json``` markers.
If no entities found, return an empty array []."""

        response = await self.llm.chat_async(prompt)
        entities = self.llm.extract_json(response)
        if not isinstance(entities, list):
            logger.warning("Entity extraction returned non-list: %s", type(entities))
            return []
        # Validate each entity has required fields
        return self._validate_entities(entities)

    def _validate_entities(self, entities) -> list[dict]:
        """Normalize and validate LLM entity output."""
        validated = []
        for ent in entities:
            if isinstance(ent, dict) and ent.get("name") and ent.get("type"):
                validated.append({
                    "name": str(ent["name"]).strip(),
                    "type": str(ent["type"]).strip().upper(),
                    "relevance": str(ent.get("relevance", "MENTIONS")).strip().upper(),
                })
        return validated

    async def extract_entities_for_sections(self, sections: list) -> list:
        """Extract entities from sections in bounded batches.

        Batching reduces LLM round trips while still processing batches
        sequentially to avoid overwhelming local Ollama/GPU resources.
        """
        for start in range(0, len(sections), self.batch_size):
            batch = sections[start:start + self.batch_size]
            if self.batch_size == 1:
                section = batch[0]
                text = section.get("summary", "") or section.get("text", "")
                if text:
                    logger.debug(
                        "Extracting entities for section %d/%d",
                        start + 1,
                        len(sections),
                    )
                    await self._extract_for_section(section, text)
                continue

            logger.debug(
                "Extracting entities for sections %d-%d/%d",
                start + 1,
                start + len(batch),
                len(sections),
            )
            await self._extract_for_batch(batch)
        return sections

    async def _extract_for_section(self, section: dict, text: str):
        """Extract entities for a single section and attach them."""
        try:
            entities = await self.extract_entities(text)
            section["_entities"] = entities
        except Exception:
            logger.exception("Entity extraction failed for section '%s'",
                             section.get("title", "?"))
            section["_entities"] = []

    async def _extract_for_batch(self, sections: list[dict]):
        """Extract entities for multiple sections in one LLM request."""
        payload = []
        section_by_index = {}
        text_by_index = {}
        for idx, section in enumerate(sections):
            text = section.get("summary", "") or section.get("text", "")
            if not text:
                section["_entities"] = []
                continue
            payload.append({
                "section_index": idx,
                "title": section.get("title", ""),
                "text": text[:self.max_chars],
            })
            section_by_index[idx] = section
            text_by_index[idx] = text

        if not payload:
            return

        try:
            by_index = await self.extract_entities_batch(payload)
            missing = set(section_by_index) - set(by_index)
            if missing:
                raise ValueError(f"Batch response missing section indexes: {sorted(missing)}")
        except Exception:
            logger.exception("Batch entity extraction failed; falling back to per-section")
            for idx, section in section_by_index.items():
                await self._extract_for_section(section, text_by_index[idx])
            return

        for idx, section in section_by_index.items():
            section["_entities"] = by_index.get(idx, [])

    async def extract_entities_batch(self, sections: list[dict]) -> dict[int, list[dict]]:
        """Extract entities for a batch of section payloads.

        Returns a mapping from section_index to normalized entity lists.
        """
        prompt = f"""Extract key entities and concepts from each section. For each entity, provide:
- name: the entity name (use the most complete/formal form)
- type: one of PERSON, ORGANIZATION, TECHNOLOGY, CONCEPT, LOCATION, EVENT, METRIC
- relevance: one of DEFINES, DISCUSSES, MENTIONS

Return ONLY valid JSON as an array of objects. Each object must have:
- section_index: the input section_index
- entities: an array of entity objects for that section

Deduplicate entities within each section. If a section has no entities, return an empty entities array.

Sections:
{json.dumps(sections)}"""

        response = await self.llm.chat_async(prompt)
        parsed = self.llm.extract_json(response)
        if not isinstance(parsed, list):
            raise ValueError(f"Batch entity extraction returned non-list: {type(parsed)}")

        by_index: dict[int, list[dict]] = {}
        for item in parsed:
            if not isinstance(item, dict):
                continue
            try:
                idx = int(item.get("section_index"))
            except (TypeError, ValueError):
                continue
            entities = item.get("entities", [])
            by_index[idx] = self._validate_entities(entities if isinstance(entities, list) else [])
        return by_index

    async def extract_relationships(self, all_entities: list[dict]) -> list[dict]:
        """Given a list of all entities, ask LLM to identify relationships between them."""
        if len(all_entities) < 2:
            return []

        entity_names = [f"- {e['name']} ({e['type']})" for e in all_entities[:50]]
        entity_list = "\n".join(entity_names)

        prompt = f"""Given these entities extracted from documents:

{entity_list}

Identify meaningful relationships between them. For each relationship, provide:
- source: entity name (must exactly match one from the list above)
- target: entity name (must exactly match one from the list above)
- relationship: one of RELATED_TO, PART_OF, USED_BY, DEPENDS_ON, COMPETES_WITH, DERIVED_FROM

Only include relationships you are confident about. Return a JSON array.
Return ONLY the JSON array wrapped in ```json``` markers.
If no relationships found, return an empty array []."""

        response = await self.llm.chat_async(prompt)
        relationships = self.llm.extract_json(response)
        if not isinstance(relationships, list):
            logger.warning("Relationship extraction returned non-list: %s", type(relationships))
            return []
        # Validate each relationship has required fields
        validated = []
        for rel in relationships:
            if (isinstance(rel, dict)
                    and rel.get("source") and rel.get("target")
                    and rel.get("relationship")):
                validated.append(rel)
        return validated
