"""Graph-powered query engine combining SQL/PGQ graph traversal with Ollama reasoning."""

import logging

logger = logging.getLogger(__name__)


class QueryEngine:
    """Answer questions by retrieving context from the document knowledge graph
    and reasoning over it with an LLM.

    Workflow:
        1. Extract key concepts from the question via Ollama.
        2. Look up graph entities matching those concepts.
        3. Retrieve relevant sections (with fallback to title substring matching).
        4. Enrich context with related entities from the graph.
        5. Build a markdown context block and send it to Ollama for reasoning.
    """

    CONCEPT_EXTRACTION_PROMPT = (
        "Extract the key concepts from the following question. "
        "Return ONLY a JSON array of strings, nothing else. "
        "Each string should be a single concept or entity mentioned in the question.\n\n"
        "Question: {question}\n\n"
        "JSON array:"
    )

    REASONING_SYSTEM_PROMPT = (
        "You are a knowledgeable assistant that answers questions based on "
        "document context retrieved from a knowledge graph. "
        "Use ONLY the provided context to answer. "
        "If the context does not contain enough information, say so clearly. "
        "Cite the document and section titles when referencing specific information."
    )

    REASONING_USER_PROMPT = (
        "Context from the knowledge graph:\n\n"
        "{context}\n\n"
        "---\n\n"
        "Question: {question}\n\n"
        "Answer:"
    )

    def __init__(self, llm, graph):
        """Initialize the query engine.

        Args:
            llm: An OllamaClient instance for LLM interaction.
            graph: A GraphStore instance for knowledge graph queries.
        """
        self.llm = llm
        self.graph = graph

    def query(self, question):
        """Answer a question using graph-retrieved context and LLM reasoning.

        Args:
            question: The user's natural language question.

        Returns:
            dict with keys:
                - answer (str): The LLM-generated answer.
                - sources (list[dict]): Each has 'title' and 'doc_name'.
                - concepts (list[str]): Extracted query concepts.
                - related_entities (list[dict]): Related entities from the graph.
        """
        # Step 1: Extract concepts from the question
        concepts = self._extract_query_concepts(question)
        logger.info(f"Extracted concepts: {concepts}")

        if not concepts:
            return {
                "answer": "I could not extract any concepts from the question. Please rephrase.",
                "sources": [],
                "concepts": [],
                "related_entities": [],
            }

        # Step 2: Find sections that mention the extracted entities
        sections_by_id = {}
        for concept in concepts:
            entity_sections = self.graph.get_entity_sections(concept)
            for sec in entity_sections:
                sid = sec["section_id"]
                if sid not in sections_by_id:
                    sections_by_id[sid] = sec

        # Step 3: Fallback — title substring match across all documents
        if not sections_by_id:
            logger.info("No entity matches found, falling back to title substring search")
            sections_by_id = self._fallback_title_search(concepts)

        # Step 4: If still nothing, return early
        if not sections_by_id:
            return {
                "answer": (
                    "No relevant information found in the knowledge graph "
                    "for the given question. Try rephrasing or using different terms."
                ),
                "sources": [],
                "concepts": concepts,
                "related_entities": [],
            }

        # Step 5: Gather related entities for context enrichment
        all_related = []
        seen_related = set()
        for concept in concepts:
            related = self.graph.get_related_entities(concept)
            for rel in related:
                rel_key = (rel.get("name") or rel.get("related_name", ""), rel.get("relationship", ""))
                if rel_key not in seen_related:
                    seen_related.add(rel_key)
                    all_related.append(rel)

        # Step 6: Build the context string
        sections_list = list(sections_by_id.values())
        context = self._build_context(sections_list, all_related)

        # Step 7: Reason over the context
        answer = self._reason(question, context)

        # Build sources list
        sources = []
        seen_sources = set()
        for sec in sections_list:
            title = sec.get("title") or sec.get("section_title", "Untitled")
            doc_name = sec.get("doc_name", "Unknown")
            source_key = (title, doc_name)
            if source_key not in seen_sources:
                seen_sources.add(source_key)
                sources.append({"title": title, "doc_name": doc_name})

        return {
            "answer": answer,
            "sources": sources,
            "concepts": concepts,
            "related_entities": [
                {
                    "name": r.get("name") or r.get("related_name", ""),
                    "type": r.get("entity_type") or r.get("related_type", ""),
                    "relationship": r.get("relationship", "RELATED_TO"),
                }
                for r in all_related
            ],
        }

    def _extract_query_concepts(self, question):
        """Ask the LLM to extract key concepts from the question.

        Returns:
            list[str]: A list of concept strings.
        """
        prompt = self.CONCEPT_EXTRACTION_PROMPT.format(question=question)
        raw_response = self.llm.chat(prompt)

        if not raw_response or raw_response == "Error":
            logger.error("LLM failed to extract concepts")
            return []

        parsed = self.llm.extract_json(raw_response)

        # extract_json may return a list directly or a dict
        if isinstance(parsed, list):
            return [str(c).strip() for c in parsed if c]
        elif isinstance(parsed, dict):
            # Some LLMs wrap the array in a key
            for value in parsed.values():
                if isinstance(value, list):
                    return [str(c).strip() for c in value if c]
            return []
        else:
            logger.warning(f"Unexpected concept extraction result type: {type(parsed)}")
            return []

    def _fallback_title_search(self, concepts):
        """Search all document sections for titles containing any of the concepts.

        This is used when no entity matches are found in the graph. It performs
        case-insensitive substring matching against section titles.

        Returns:
            dict: section_id -> section dict
        """
        sections_by_id = {}
        documents = self.graph.get_all_documents()
        concepts_lower = [c.lower() for c in concepts]

        for doc in documents:
            doc_sections = self.graph.get_document_sections(doc["doc_id"])
            for sec in doc_sections:
                title = (sec.get("title") or "").lower()
                for concept_lower in concepts_lower:
                    if concept_lower in title:
                        sid = sec["section_id"]
                        if sid not in sections_by_id:
                            # Attach doc_name for source tracking
                            sec["doc_name"] = doc.get("doc_name", "Unknown")
                            sections_by_id[sid] = sec
                        break  # No need to check remaining concepts for this section

        logger.info(f"Fallback title search found {len(sections_by_id)} section(s)")
        return sections_by_id

    def _build_context(self, sections, related_entities):
        """Build a markdown-formatted context string from sections and related entities.

        Args:
            sections: List of section dicts with title, summary/text_content, doc_name.
            related_entities: List of related entity dicts.

        Returns:
            str: Formatted markdown context.
        """
        parts = []

        # Relevant document sections
        parts.append("## Relevant Document Sections\n")
        for sec in sections:
            title = sec.get("title") or sec.get("section_title", "Untitled")
            doc_name = sec.get("doc_name", "Unknown")
            depth = sec.get("depth_level", 0)
            relevance = sec.get("relevance", "")

            parts.append(f"### {title}")
            parts.append(f"**Document:** {doc_name} | **Depth:** {depth}")
            if relevance:
                parts.append(f"**Relevance:** {relevance}")

            # Prefer text_content, fall back to summary
            content = sec.get("text_content") or sec.get("summary") or ""
            if content:
                parts.append(f"\n{content}")
            parts.append("")  # blank line separator

        # Related concepts
        if related_entities:
            parts.append("## Related Concepts\n")
            for ent in related_entities:
                name = ent.get("name") or ent.get("related_name", "")
                ent_type = ent.get("entity_type") or ent.get("related_type", "")
                relationship = ent.get("relationship", "RELATED_TO")
                description = ent.get("description", "")

                entry = f"- **{name}** ({ent_type}) — _{relationship}_"
                if description:
                    entry += f": {description}"
                parts.append(entry)
            parts.append("")

        return "\n".join(parts)

    def _reason(self, question, context):
        """Send the context and question to the LLM for a reasoned answer.

        Args:
            question: The user's original question.
            context: The markdown-formatted context string.

        Returns:
            str: The LLM's answer.
        """
        chat_history = [
            {"role": "system", "content": self.REASONING_SYSTEM_PROMPT},
        ]
        prompt = self.REASONING_USER_PROMPT.format(context=context, question=question)

        answer = self.llm.chat(prompt, chat_history=chat_history)
        if not answer or answer == "Error":
            return "An error occurred while generating the answer. Please try again."

        return answer
