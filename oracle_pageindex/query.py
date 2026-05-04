"""Graph-powered query engine combining intent classification, multi-hop
SQL/PGQ graph traversal, and Ollama reasoning."""

import logging

from .llm import OllamaError
from .models import GraphQuery, QueryIntent, QueryResult, TraversalStep
from .utils import count_tokens

logger = logging.getLogger(__name__)

# Maximum tokens of context to send to the LLM for reasoning
_MAX_CONTEXT_TOKENS = 12_000
# Maximum allowed query length (characters)
MAX_QUERY_LENGTH = 5_000


class QueryEngine:
    """Answer questions by classifying intent, traversing the document
    knowledge graph via multi-hop SQL/PGQ queries, and reasoning over
    the assembled context with an LLM.

    Workflow:
        1. Classify the question's intent and extract entities via Ollama.
        2. Resolve entity names to graph IDs.
        3. Dispatch to intent-specific traversal strategies.
        4. Fall back to title substring search when traversal yields nothing.
        5. Build a token-budgeted markdown context block.
        6. Reason over the context with Ollama.
        7. Return a QueryResult dataclass with answer, sources, traversal
           metadata, and the SQL/PGQ queries that were executed.
    """

    REASONING_SYSTEM_PROMPT = (
        "You are a knowledgeable assistant that answers questions based on "
        "document context retrieved from a knowledge graph. "
        "Use ONLY the provided context to answer. "
        "If the context does not contain enough information, say so clearly. "
        "Cite the document and section titles when referencing specific information. "
        "Do NOT invent or hallucinate information not present in the context."
    )

    REASONING_USER_PROMPT = (
        "Context from the knowledge graph:\n\n"
        "{context}\n\n"
        "---\n\n"
        "Question: <<{question}>>\n\n"
        "Answer based ONLY on the context above:"
    )

    def __init__(self, llm, graph):
        self.llm = llm
        self.graph = graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def query(self, question: str, session_id: int | None = None) -> QueryResult:
        """Answer a question using intent-driven graph traversal and LLM reasoning.

        Args:
            question: The user's natural language question (max 5000 chars).
            session_id: Optional conversation session ID. When provided,
                previous turn context is loaded and used to supplement entity
                resolution. When ``None``, a new session is created automatically.

        Returns:
            QueryResult dataclass with answer, sources, traversal path, etc.
        """
        if len(question) > MAX_QUERY_LENGTH:
            question = question[:MAX_QUERY_LENGTH]

        # -- Session management (graceful: never breaks the query) ----------
        turn_id: int | None = None
        turn_number: int = 1
        session_context: dict | None = None
        try:
            if session_id is not None:
                session_context = self.graph.get_session_context(session_id)
                turns = self.graph.get_session_turns(session_id)
                turn_number = len(turns) + 1
            else:
                session_id = self.graph.create_session(title=question[:100])
                session_context = None
                turn_number = 1
        except Exception:
            logger.debug("Session management unavailable, continuing without it", exc_info=True)

        # Step 1: Classify intent and extract entities
        intent, entity_names = self.llm.classify_intent(question)
        logger.info(f"Intent: {intent.value}, Entities: {entity_names}")

        # Create turn record (after intent classification so we can store the intent)
        try:
            intent_str = intent.value if hasattr(intent, "value") else str(intent)
            turn_id = self.graph.create_turn(session_id, turn_number, question, intent_str)
        except Exception:
            logger.debug("Failed to create turn record", exc_info=True)

        if not entity_names:
            self._update_turn_answer(turn_id, "I could not extract any concepts from the question. Please rephrase.")
            return QueryResult(
                answer="I could not extract any concepts from the question. Please rephrase.",
                sources=[],
                concepts=[],
                session_id=session_id,
            )

        # Step 2: Resolve entity names to graph records (with IDs)
        resolved = self._resolve_entity_ids(entity_names)

        # Supplement with entities from previous turns in the session
        if session_context and session_context.get("primary_entities"):
            resolved_names = {e.get("name", "").lower() for e in resolved}
            for prev_ent in session_context["primary_entities"]:
                prev_name = prev_ent if isinstance(prev_ent, str) else prev_ent.get("name", "")
                if prev_name.lower() not in resolved_names:
                    extra = self._resolve_entity_ids([prev_name])
                    resolved.extend(extra)
                    resolved_names.add(prev_name.lower())

        # Step 3: Dispatch by intent
        graph_queries: list[GraphQuery] = []
        traversal_steps: list[TraversalStep] = []
        sections_by_id: dict[int, dict] = {}
        all_related: list[dict] = []

        if resolved:
            sections_by_id, all_related, graph_queries, traversal_steps = (
                self._dispatch_by_intent(intent, entity_names, resolved)
            )

        # Step 4: Fallback to entity-section LIKE matching
        if not sections_by_id and resolved:
            for ent in resolved:
                ent_name = ent.get("name", "")
                for sec in self.graph.get_entity_sections(ent_name):
                    sid = sec["section_id"]
                    if sid not in sections_by_id:
                        sections_by_id[sid] = sec

        # Step 5: Fallback to title substring search
        if not sections_by_id:
            logger.info("No entity matches found, falling back to title substring search")
            sections_by_id = self._fallback_title_search(entity_names)

        if sections_by_id:
            sections_by_id = self._hydrate_sections(sections_by_id)
        all_related = self._dedupe_related_entities(all_related)

        # Step 6: If still nothing, return early
        if not sections_by_id:
            no_info_answer = (
                "No relevant information found in the knowledge graph "
                "for the given question. Try rephrasing or using different terms."
            )
            self._update_turn_answer(turn_id, no_info_answer)
            return QueryResult(
                answer=no_info_answer,
                sources=[],
                concepts=entity_names,
                graph_queries=graph_queries,
                traversal_path=traversal_steps,
                session_id=session_id,
            )

        # Step 7: Build context and reason
        sections_list = list(sections_by_id.values())
        context = self._build_context(sections_list, all_related)
        answer = self._reason(question, context)

        # -- Record turn edges (entities + sections) -----------------------
        self._record_turn_entities(turn_id, resolved, all_related)
        self._record_turn_sections(turn_id, sections_list)
        self._update_turn_answer(turn_id, answer)

        # Build sources list (deduplicated)
        sources = []
        seen_sources: set[tuple[str, str]] = set()
        for sec in sections_list:
            title = sec.get("title") or sec.get("section_title", "Untitled")
            doc_name = sec.get("doc_name", "Unknown")
            source_key = (title, doc_name)
            if source_key not in seen_sources:
                seen_sources.add(source_key)
                sources.append({"title": title, "doc_name": doc_name})

        # Build related entities output
        related_out = [
            {
                "name": r.get("name") or r.get("related_name", ""),
                "type": r.get("entity_type") or r.get("related_type", ""),
                "relationship": r.get("relationship", "RELATED_TO"),
            }
            for r in all_related
        ]

        return QueryResult(
            answer=answer,
            sources=sources,
            concepts=entity_names,
            related_entities=related_out,
            graph_queries=graph_queries,
            traversal_path=traversal_steps,
            session_id=session_id,
        )

    # ------------------------------------------------------------------
    # Intent dispatch
    # ------------------------------------------------------------------

    def _dispatch_by_intent(
        self,
        intent: QueryIntent,
        entity_names: list[str],
        resolved: list[dict],
    ) -> tuple[dict, list[dict], list[GraphQuery], list[TraversalStep]]:
        """Route to the correct traversal strategy based on classified intent."""
        handler = {
            QueryIntent.LOOKUP: self._handle_lookup,
            QueryIntent.RELATIONSHIP: self._handle_relationship,
            QueryIntent.EXPLORATION: self._handle_exploration,
            QueryIntent.COMPARISON: self._handle_comparison,
            QueryIntent.HIERARCHICAL: self._handle_hierarchical,
            QueryIntent.TEMPORAL: self._handle_exploration,  # placeholder, falls back to exploration
        }.get(intent, self._handle_exploration)

        return handler(entity_names, resolved)

    # ------------------------------------------------------------------
    # Intent handlers
    # ------------------------------------------------------------------

    def _handle_lookup(
        self, entity_names: list[str], resolved: list[dict]
    ) -> tuple[dict, list[dict], list[GraphQuery], list[TraversalStep]]:
        """LOOKUP: traverse entity neighborhood for each resolved entity."""
        sections_by_id: dict[int, dict] = {}
        all_related: list[dict] = []
        graph_queries: list[GraphQuery] = []
        traversal_steps: list[TraversalStep] = []
        step_num = 0

        for ent in resolved:
            eid = ent["entity_id"]
            result = self.graph.traverse_entity_neighborhood(eid)
            gq = result.get("graph_query")
            if gq:
                graph_queries.append(gq)

            for sec in result.get("sections", []):
                sid = sec["section_id"]
                if sid not in sections_by_id:
                    sections_by_id[sid] = sec
                    step_num += 1
                    traversal_steps.append(TraversalStep(
                        step_number=step_num,
                        node_type="section",
                        node_id=sid,
                        node_label=sec.get("title", ""),
                        edge_label="mentions",
                        edge_direction="inbound",
                        reason=f"Section mentions entity '{ent.get('name', '')}'",
                    ))

            for co_ent in result.get("entities", []):
                all_related.append(co_ent)

        return sections_by_id, all_related, graph_queries, traversal_steps

    def _handle_relationship(
        self, entity_names: list[str], resolved: list[dict]
    ) -> tuple[dict, list[dict], list[GraphQuery], list[TraversalStep]]:
        """RELATIONSHIP: find paths between entity pairs + neighborhood for each."""
        sections_by_id: dict[int, dict] = {}
        all_related: list[dict] = []
        graph_queries: list[GraphQuery] = []
        traversal_steps: list[TraversalStep] = []
        step_num = 0

        # Path finding between pairs
        if len(resolved) >= 2:
            for i in range(len(resolved) - 1):
                src_name = resolved[i].get("name", "")
                tgt_name = resolved[i + 1].get("name", "")
                path_result = self.graph.find_entity_paths(src_name, tgt_name)
                gq = path_result.get("graph_query")
                if gq:
                    graph_queries.append(gq)

                for path in path_result.get("paths", []):
                    mid_name = path.get("mid_name", "")
                    step_num += 1
                    traversal_steps.append(TraversalStep(
                        step_number=step_num,
                        node_type="entity",
                        node_id=path.get("mid_id", 0),
                        node_label=mid_name,
                        edge_label=path.get("r1_type", "RELATED_TO"),
                        edge_direction="outbound",
                        reason=f"Path: {src_name} -> {mid_name} -> {tgt_name}",
                    ))

        # Also get neighborhood for each entity
        for ent in resolved:
            eid = ent["entity_id"]
            result = self.graph.traverse_entity_neighborhood(eid)
            gq = result.get("graph_query")
            if gq:
                graph_queries.append(gq)

            for sec in result.get("sections", []):
                sid = sec["section_id"]
                if sid not in sections_by_id:
                    sections_by_id[sid] = sec

            for co_ent in result.get("entities", []):
                all_related.append(co_ent)

        return sections_by_id, all_related, graph_queries, traversal_steps

    def _handle_exploration(
        self, entity_names: list[str], resolved: list[dict]
    ) -> tuple[dict, list[dict], list[GraphQuery], list[TraversalStep]]:
        """EXPLORATION / TEMPORAL: neighborhood + multi-hop expansion."""
        sections_by_id: dict[int, dict] = {}
        all_related: list[dict] = []
        graph_queries: list[GraphQuery] = []
        traversal_steps: list[TraversalStep] = []
        step_num = 0

        for ent in resolved:
            eid = ent["entity_id"]

            # Neighborhood traversal
            nbr = self.graph.traverse_entity_neighborhood(eid)
            gq = nbr.get("graph_query")
            if gq:
                graph_queries.append(gq)

            for sec in nbr.get("sections", []):
                sid = sec["section_id"]
                if sid not in sections_by_id:
                    sections_by_id[sid] = sec
                    step_num += 1
                    traversal_steps.append(TraversalStep(
                        step_number=step_num,
                        node_type="section",
                        node_id=sid,
                        node_label=sec.get("title", ""),
                        edge_label="mentions",
                        edge_direction="inbound",
                        reason=f"Section mentions entity '{ent.get('name', '')}'",
                    ))

            for co_ent in nbr.get("entities", []):
                all_related.append(co_ent)

            # Multi-hop expansion for broader reach
            multi = self.graph.get_multi_hop_entities(eid)
            gq2 = multi.get("graph_query")
            if gq2:
                graph_queries.append(gq2)

            for mh_ent in multi.get("entities", []):
                step_num += 1
                traversal_steps.append(TraversalStep(
                    step_number=step_num,
                    node_type="entity",
                    node_id=mh_ent.get("entity_id", 0),
                    node_label=mh_ent.get("name", ""),
                    edge_label=mh_ent.get("relationship", "RELATED_TO"),
                    edge_direction="outbound",
                    reason=f"Multi-hop entity from '{ent.get('name', '')}'",
                ))
                all_related.append(mh_ent)

        return sections_by_id, all_related, graph_queries, traversal_steps

    def _handle_comparison(
        self, entity_names: list[str], resolved: list[dict]
    ) -> tuple[dict, list[dict], list[GraphQuery], list[TraversalStep]]:
        """COMPARISON: separate neighborhood per entity, then combine."""
        sections_by_id: dict[int, dict] = {}
        all_related: list[dict] = []
        graph_queries: list[GraphQuery] = []
        traversal_steps: list[TraversalStep] = []
        step_num = 0

        for ent in resolved:
            eid = ent["entity_id"]
            result = self.graph.traverse_entity_neighborhood(eid)
            gq = result.get("graph_query")
            if gq:
                graph_queries.append(gq)

            for sec in result.get("sections", []):
                sid = sec["section_id"]
                if sid not in sections_by_id:
                    sections_by_id[sid] = sec
                    step_num += 1
                    traversal_steps.append(TraversalStep(
                        step_number=step_num,
                        node_type="section",
                        node_id=sid,
                        node_label=sec.get("title", ""),
                        edge_label="mentions",
                        edge_direction="inbound",
                        reason=f"Comparison context for '{ent.get('name', '')}'",
                    ))

            for co_ent in result.get("entities", []):
                all_related.append(co_ent)

        return sections_by_id, all_related, graph_queries, traversal_steps

    def _handle_hierarchical(
        self, entity_names: list[str], resolved: list[dict]
    ) -> tuple[dict, list[dict], list[GraphQuery], list[TraversalStep]]:
        """HIERARCHICAL: find sections via entities, then traverse descendants."""
        sections_by_id: dict[int, dict] = {}
        all_related: list[dict] = []
        graph_queries: list[GraphQuery] = []
        traversal_steps: list[TraversalStep] = []
        step_num = 0

        for ent in resolved:
            ent_name = ent.get("name", "")
            ent_sections = self.graph.get_entity_sections(ent_name)

            for sec in ent_sections:
                sid = sec["section_id"]
                if sid not in sections_by_id:
                    sections_by_id[sid] = sec

                # Traverse descendants of each matched section
                descendants = self.graph.traverse_section_descendants(sid)
                for desc in descendants:
                    desc_id = desc["section_id"]
                    if desc_id not in sections_by_id:
                        sections_by_id[desc_id] = desc
                        step_num += 1
                        traversal_steps.append(TraversalStep(
                            step_number=step_num,
                            node_type="section",
                            node_id=desc_id,
                            node_label=desc.get("title", ""),
                            edge_label="parent_of",
                            edge_direction="outbound",
                            reason=f"Descendant of section '{sec.get('title', '')}'",
                        ))

        return sections_by_id, all_related, graph_queries, traversal_steps

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _update_turn_answer(self, turn_id: int | None, answer: str) -> None:
        """Persist the answer for a turn. Silently ignored when session tables are unavailable."""
        if turn_id is None:
            return
        try:
            self.graph.update_turn_answer(turn_id, answer)
        except Exception:
            logger.debug("Failed to update turn answer for turn_id=%s", turn_id, exc_info=True)

    def _record_turn_entities(
        self, turn_id: int | None, primary: list[dict], related: list[dict]
    ) -> None:
        """Record which entities a turn touched. Failures are silently ignored."""
        if turn_id is None:
            return
        seen: set[int] = set()
        for ent in primary:
            eid = ent.get("entity_id")
            if eid and eid not in seen:
                seen.add(eid)
                try:
                    self.graph.insert_turn_entity(turn_id, eid, "PRIMARY")
                except Exception:
                    logger.debug("Failed to record PRIMARY turn entity %s", eid, exc_info=True)
        for ent in related:
            eid = ent.get("entity_id")
            if eid and eid not in seen:
                seen.add(eid)
                try:
                    self.graph.insert_turn_entity(turn_id, eid, "REFERENCED")
                except Exception:
                    logger.debug("Failed to record REFERENCED turn entity %s", eid, exc_info=True)

    def _record_turn_sections(self, turn_id: int | None, sections: list[dict]) -> None:
        """Record which sections a turn used for context. Failures are silently ignored."""
        if turn_id is None:
            return
        for i, sec in enumerate(sections):
            sid = sec.get("section_id")
            if sid:
                try:
                    self.graph.insert_turn_section(turn_id, sid, rank_score=1.0 - (i * 0.1))
                except Exception:
                    logger.debug("Failed to record turn section %s", sid, exc_info=True)

    def _resolve_entity_ids(self, entity_names: list[str]) -> list[dict]:
        """Resolve entity name strings to entity records with IDs."""
        resolved = []
        all_entities = self.graph.get_all_entities()
        for name in entity_names:
            name_lower = name.lower()
            for ent in all_entities:
                if name_lower in ent.get("name", "").lower():
                    resolved.append(ent)
                    break
        return resolved

    def _fallback_title_search(self, concepts: list[str]) -> dict:
        """Search all document sections for titles containing any of the concepts."""
        sections_by_id: dict[int, dict] = {}
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
                            sec["doc_name"] = doc.get("doc_name", "Unknown")
                            sections_by_id[sid] = sec
                        break

        logger.info(f"Fallback title search found {len(sections_by_id)} section(s)")
        return sections_by_id

    def _hydrate_sections(self, sections_by_id: dict[int, dict]) -> dict[int, dict]:
        """Merge traversal hits with full section text and document metadata."""
        section_ids = list(sections_by_id)
        if not section_ids:
            return sections_by_id

        try:
            full_sections = self.graph.get_sections_by_ids(section_ids)
        except Exception:
            logger.debug("Failed to hydrate section context", exc_info=True)
            return sections_by_id

        hydrated = {}
        for sid, section in sections_by_id.items():
            merged = dict(full_sections.get(sid, {}))
            for key, value in section.items():
                if value not in (None, ""):
                    merged[key] = value
            hydrated[sid] = merged
        return hydrated

    def _dedupe_related_entities(self, related_entities: list[dict]) -> list[dict]:
        """Remove duplicate related entities while preserving first-seen order."""
        seen = set()
        deduped = []
        for ent in related_entities:
            key = ent.get("entity_id")
            if key is None:
                key = (
                    ent.get("name") or ent.get("related_name", ""),
                    ent.get("entity_type") or ent.get("related_type", ""),
                    ent.get("relationship", "RELATED_TO"),
                )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(ent)
        return deduped

    def _build_context(self, sections: list, related_entities: list) -> str:
        """Build a markdown-formatted context string, respecting the token budget.

        Sections are added in order until the token budget is exhausted.
        Related entities are appended at the end if budget allows.
        """
        parts = []
        token_budget = _MAX_CONTEXT_TOKENS
        tokens_used = 0

        parts.append("## Relevant Document Sections\n")
        tokens_used += count_tokens(parts[0])

        for sec in sections:
            title = sec.get("title") or sec.get("section_title", "Untitled")
            doc_name = sec.get("doc_name", "Unknown")
            depth = sec.get("depth_level", 0)
            relevance = sec.get("relevance", "")

            section_parts = [f"### {title}"]
            section_parts.append(f"**Document:** {doc_name} | **Depth:** {depth}")
            if relevance:
                section_parts.append(f"**Relevance:** {relevance}")

            content = sec.get("text_content") or sec.get("summary") or ""
            if content:
                section_parts.append(f"\n{content}")
            section_parts.append("")

            section_text = "\n".join(section_parts)
            section_tokens = count_tokens(section_text)

            if tokens_used + section_tokens > token_budget:
                # Try truncating the content to fit remaining budget
                remaining = token_budget - tokens_used
                if remaining > 200:  # Worth including a truncated version
                    truncated = content[:remaining * 3]  # rough char estimate
                    section_parts = [f"### {title}", f"**Document:** {doc_name}",
                                     f"\n{truncated}\n[...truncated...]", ""]
                    section_text = "\n".join(section_parts)
                    parts.append(section_text)
                break

            parts.append(section_text)
            tokens_used += section_tokens

        # Related concepts (if budget allows)
        if related_entities and tokens_used < token_budget - 200:
            rel_parts = ["## Related Concepts\n"]
            for ent in related_entities:
                name = ent.get("name") or ent.get("related_name", "")
                ent_type = ent.get("entity_type") or ent.get("related_type", "")
                relationship = ent.get("relationship", "RELATED_TO")
                description = ent.get("description", "")

                entry = f"- **{name}** ({ent_type}) — _{relationship}_"
                if description:
                    entry += f": {description}"
                rel_parts.append(entry)

                tokens_used += count_tokens(entry)
                if tokens_used >= token_budget:
                    break
            rel_parts.append("")
            parts.append("\n".join(rel_parts))

        return "\n".join(parts)

    def _reason(self, question: str, context: str) -> str:
        """Send the context and question to the LLM for a reasoned answer."""
        chat_history = [
            {"role": "system", "content": self.REASONING_SYSTEM_PROMPT},
        ]
        prompt = self.REASONING_USER_PROMPT.format(context=context, question=question)

        try:
            answer = self.llm.chat(prompt, chat_history=chat_history)
        except OllamaError:
            return "An error occurred while generating the answer. Please try again."

        return answer
