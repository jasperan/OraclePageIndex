import asyncio
import logging

logger = logging.getLogger(__name__)


class EntityExtractor:
    def __init__(self, llm):
        self.llm = llm

    async def extract_entities(self, text):
        """Extract named entities and concepts from text using Ollama."""
        prompt = f"""Extract key entities and concepts from this text. For each entity, provide:
- name: the entity name
- type: one of PERSON, ORGANIZATION, TECHNOLOGY, CONCEPT, LOCATION, EVENT, METRIC
- relevance: one of DEFINES (text defines this entity), DISCUSSES (text discusses it in depth), MENTIONS (brief reference)

Text:
{text[:4000]}

Return a JSON array of objects. Return ONLY the JSON array wrapped in ```json``` markers.
If no entities found, return an empty array []."""

        response = await self.llm.chat_async(prompt)
        entities = self.llm.extract_json(response)
        if not isinstance(entities, list):
            return []
        return entities

    async def extract_entities_for_sections(self, sections):
        """Extract entities from sections sequentially to avoid GPU OOM."""
        for section in sections:
            text = section.get("text", "") or section.get("summary", "")
            if text:
                await self._extract_for_section(section, text)
        return sections

    async def _extract_for_section(self, section, text):
        """Extract entities for a single section and attach them."""
        entities = await self.extract_entities(text)
        section["_entities"] = entities

    async def extract_relationships(self, all_entities):
        """Given a list of all entities, ask LLM to identify relationships between them."""
        if len(all_entities) < 2:
            return []

        entity_names = [f"- {e['name']} ({e['type']})" for e in all_entities[:50]]
        entity_list = "\n".join(entity_names)

        prompt = f"""Given these entities extracted from documents:

{entity_list}

Identify meaningful relationships between them. For each relationship, provide:
- source: entity name
- target: entity name
- relationship: one of RELATED_TO, PART_OF, USED_BY, DEPENDS_ON, COMPETES_WITH, DERIVED_FROM

Only include relationships you are confident about. Return a JSON array.
Return ONLY the JSON array wrapped in ```json``` markers.
If no relationships found, return an empty array []."""

        response = await self.llm.chat_async(prompt)
        relationships = self.llm.extract_json(response)
        if not isinstance(relationships, list):
            return []
        return relationships
