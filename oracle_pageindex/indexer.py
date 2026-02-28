"""
Document indexing pipeline for OraclePageIndex.

Orchestrates the full flow: parse PDF -> extract entities -> store in graph.
Ties together DocumentParser, EntityExtractor, and GraphStore into a single
`index_pdf()` call that returns indexing statistics.
"""

import asyncio
import logging

from .entity_extractor import EntityExtractor
from .graph import GraphStore
from .parser import DocumentParser

logger = logging.getLogger(__name__)


class Indexer:
    """Orchestrates the document indexing pipeline.

    Parameters
    ----------
    llm : OllamaClient
        Pre-configured Ollama client for LLM interactions.
    db : OracleDB
        Pre-configured Oracle database connection.
    opt : SimpleNamespace
        Configuration options (from ConfigLoader).
    """

    def __init__(self, llm, db, opt):
        self.llm = llm
        self.db = db
        self.opt = opt

        # Internal components
        self.parser = DocumentParser(
            llm=llm,
            toc_check_page_num=getattr(opt, "toc_check_page_num", 20),
            max_token_num_each_node=getattr(opt, "max_token_num_each_node", 20_000),
            pdf_parser=getattr(opt, "pdf_parser", "PyMuPDF"),
            add_node_id=getattr(opt, "if_add_node_id", "yes") == "yes",
            add_summaries=getattr(opt, "if_add_node_summary", "yes") == "yes",
        )
        self.extract_entities = getattr(opt, "if_extract_entities", "yes") == "yes"
        self.extractor = EntityExtractor(llm=llm)
        self.graph = GraphStore(db=db)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def index_pdf(self, pdf_path):
        """Run the full indexing pipeline on a PDF.

        Steps:
            1. Parse PDF into a structured tree with summaries.
            2. Insert document vertex into the graph.
            3. Recursively insert tree nodes as section vertices with
               hierarchy edges.
            4. Extract entities for every section via the LLM.
            5. Upsert entities and create mention edges.
            6. Extract inter-entity relationships and store them.

        Parameters
        ----------
        pdf_path : str
            Path to the PDF file to index.

        Returns
        -------
        dict
            Statistics: ``{"doc_id", "doc_name", "sections", "entities",
            "relationships"}``.
        """
        # -- Step 1: Parse the PDF -----------------------------------------
        logger.info(f"Indexing PDF: {pdf_path}")
        result = self.parser.build_tree(pdf_path)
        doc_name = result["doc_name"]
        tree = result["structure"]
        page_list = result["page_list"]
        logger.info(f"Parsed document '{doc_name}' with {len(page_list)} pages")

        # -- Step 2: Insert document vertex --------------------------------
        doc_description = getattr(self.opt, "doc_description", "")
        doc_id = self.graph.insert_document(
            doc_name=doc_name,
            doc_description=doc_description,
            source_path=str(pdf_path),
        )
        logger.info(f"Created document vertex: doc_id={doc_id}")

        # -- Step 3: Insert tree nodes as sections -------------------------
        all_sections = []
        self._insert_tree_nodes(
            tree, doc_id, parent_section_id=None, depth=0, all_sections=all_sections
        )
        logger.info(f"Inserted {len(all_sections)} section(s) into the graph")

        # -- Steps 4-6: Entity extraction (optional, can be slow) ----------
        unique_entities = []
        relationships = []

        if self.extract_entities:
            # -- Step 4: Extract entities for each section -------------------
            loop = _get_or_create_event_loop()
            loop.run_until_complete(
                self.extractor.extract_entities_for_sections(all_sections)
            )
            logger.info("Entity extraction complete for all sections")

            # -- Step 5: Upsert entities & create mention edges -------------
            entity_name_to_id = {}  # (name, type) -> entity_id

            for section in all_sections:
                section_id = section["_section_id"]
                entities = section.get("_entities", [])

                for ent in entities:
                    name = ent.get("name", "").strip()
                    etype = ent.get("type", "CONCEPT").strip()
                    relevance = ent.get("relevance", "MENTIONS").strip()

                    if not name:
                        continue

                    key = (name, etype)
                    if key not in entity_name_to_id:
                        entity_id = self.graph.upsert_entity(
                            name=name,
                            entity_type=etype,
                            description="",
                        )
                        entity_name_to_id[key] = entity_id
                        unique_entities.append(
                            {"name": name, "type": etype, "entity_id": entity_id}
                        )

                    entity_id = entity_name_to_id[key]
                    self.graph.insert_mention_edge(
                        section_id=section_id,
                        entity_id=entity_id,
                        relevance=relevance,
                    )

            logger.info(f"Upserted {len(unique_entities)} unique entity/entities")

            # -- Step 6: Extract and store inter-entity relationships -------
            if len(unique_entities) >= 2:
                relationships = loop.run_until_complete(
                    self.extractor.extract_relationships(unique_entities)
                )

                name_to_id = {}
                for ent in unique_entities:
                    name_to_id[ent["name"]] = ent["entity_id"]

                stored_rels = 0
                for rel in relationships:
                    source_name = rel.get("source", "").strip()
                    target_name = rel.get("target", "").strip()
                    relationship = rel.get("relationship", "RELATED_TO").strip()

                    source_id = name_to_id.get(source_name)
                    target_id = name_to_id.get(target_name)

                    if source_id is not None and target_id is not None:
                        self.graph.insert_entity_relationship(
                            source_id=source_id,
                            target_id=target_id,
                            relationship=relationship,
                        )
                        stored_rels += 1
                    else:
                        logger.warning(
                            f"Skipping relationship '{source_name}' -> '{target_name}': "
                            f"entity not found in index"
                        )

                relationships = relationships[:stored_rels] if stored_rels else []
                logger.info(f"Stored {stored_rels} entity relationship(s)")
        else:
            logger.info("Skipping entity extraction (disabled in config)")

        # -- Build stats and return ----------------------------------------
        stats = {
            "doc_id": doc_id,
            "doc_name": doc_name,
            "sections": len(all_sections),
            "entities": len(unique_entities),
            "relationships": len(relationships),
        }
        logger.info(f"Indexing complete: {stats}")
        return stats

    # ------------------------------------------------------------------
    # Internal: recursive tree insertion
    # ------------------------------------------------------------------

    def _insert_tree_nodes(self, node, doc_id, parent_section_id, depth, all_sections):
        """Recursively walk the parsed tree, inserting each node as a
        section vertex and creating hierarchy edges.

        Handles both list and dict inputs:
        - list: iterate and recurse into each element
        - dict: insert the node, then recurse into ``node["nodes"]`` children

        Parameters
        ----------
        node : dict | list
            Current tree node or list of nodes.
        doc_id : int
            Parent document ID.
        parent_section_id : int | None
            Section ID of the parent node (None for root-level nodes).
        depth : int
            Current depth level in the tree (0 = root).
        all_sections : list
            Accumulator list; each inserted section dict is appended
            with a ``_section_id`` key for downstream entity extraction.
        """
        if isinstance(node, list):
            for child in node:
                self._insert_tree_nodes(
                    child, doc_id, parent_section_id, depth, all_sections
                )
            return

        if not isinstance(node, dict):
            return

        # Extract node fields
        title = node.get("title", "")
        node_id = node.get("node_id", "")
        summary = node.get("summary", "")
        text_content = node.get("text", "")
        start_index = node.get("start_index")
        end_index = node.get("end_index")

        # Insert section vertex
        section_id = self.graph.insert_section(
            doc_id=doc_id,
            node_id=node_id,
            title=title,
            summary=summary,
            text_content=text_content,
            start_index=start_index,
            end_index=end_index,
            depth_level=depth,
        )

        # Create hierarchy edge if this is a child node
        if parent_section_id is not None:
            self.graph.insert_hierarchy_edge(
                parent_id=parent_section_id,
                child_id=section_id,
            )

        # Collect section info for entity extraction
        section_info = {
            "_section_id": section_id,
            "title": title,
            "text": text_content,
            "summary": summary,
        }
        all_sections.append(section_info)

        # Recurse into children
        children = node.get("nodes", [])
        if children:
            self._insert_tree_nodes(
                children, doc_id, parent_section_id=section_id,
                depth=depth + 1, all_sections=all_sections,
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_or_create_event_loop():
    """Get the running event loop or create a new one.

    Needed because the entity extractor uses async methods, but the
    indexer's public API is synchronous.  When running inside Jupyter
    (which already has a running event loop), nest_asyncio is applied
    so that ``loop.run_until_complete`` can be called without conflict.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
        # If the loop is already running (e.g. inside Jupyter), patch it.
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply(loop)
        return loop
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop
