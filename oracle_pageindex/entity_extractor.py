import logging

logger = logging.getLogger(__name__)


class EntityExtractor:
    def __init__(self, llm):
        self.llm = llm

    async def extract_entities(self, text: str) -> list[dict]:
        """Extract named entities and concepts from text using Ollama."""
        prompt = f"""Extract key entities and concepts from this text. For each entity, provide:
- name: the entity name (use the most complete/formal form, e.g. "Apple Inc." not "Apple")
- type: one of PERSON, ORGANIZATION, TECHNOLOGY, CONCEPT, LOCATION, EVENT, METRIC
- relevance: one of DEFINES (text defines this entity), DISCUSSES (text discusses it in depth), MENTIONS (brief reference)

Only include entities you are confident about. Deduplicate: if the same entity appears with different names (e.g. "ML" and "Machine Learning"), use the most formal name.

Text:
<<{text[:4000]}>>

Return a JSON array of objects. Return ONLY the JSON array wrapped in ```json``` markers.
If no entities found, return an empty array []."""

        response = await self.llm.chat_async(prompt)
        entities = self.llm.extract_json(response)
        if not isinstance(entities, list):
            logger.warning("Entity extraction returned non-list: %s", type(entities))
            return []
        # Validate each entity has required fields
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
        """Extract entities from sections sequentially to avoid GPU OOM."""
        for i, section in enumerate(sections):
            text = section.get("text", "") or section.get("summary", "")
            if text:
                logger.debug("Extracting entities for section %d/%d", i + 1, len(sections))
                await self._extract_for_section(section, text)
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
