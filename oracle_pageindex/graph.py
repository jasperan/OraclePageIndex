import logging
import time

from oracle_pageindex.models import GraphQuery

logger = logging.getLogger(__name__)


class GraphStore:
    """CRUD operations for the OraclePageIndex document knowledge graph.

    All SQL uses Oracle-style :param bind variables.
    INSERT...RETURNING uses the RETURNING col INTO :out_id pattern
    compatible with OracleDB.execute_returning().
    """

    def __init__(self, db):
        self.db = db

    # ------------------------------------------------------------------
    # Insert methods
    # ------------------------------------------------------------------

    def insert_document(self, doc_name, doc_description, source_path,
                        doc_group=None, doc_version=1):
        """Insert a document vertex and return its doc_id.

        Parameters
        ----------
        doc_name : str
            Human-readable document name.
        doc_description : str
            Short description of the document.
        source_path : str
            Filesystem path to the source PDF.
        doc_group : str | None
            Optional group identifier for temporal versioning (e.g. "apple-10k").
            Documents in the same group are treated as successive versions.
        doc_version : int
            Version number within the group (default 1).
        """
        sql = """
            INSERT INTO documents (doc_name, doc_description, source_path, doc_group, doc_version)
            VALUES (:doc_name, :doc_description, :source_path, :doc_group, :doc_version)
            RETURNING doc_id INTO :out_id
        """
        doc_id = self.db.execute_returning(
            sql,
            {
                "doc_name": doc_name,
                "doc_description": doc_description,
                "source_path": source_path,
                "doc_group": doc_group,
                "doc_version": doc_version,
            },
            returning_col="id",
        )
        logger.info(
            f"Inserted document '{doc_name}' (group={doc_group}, v{doc_version}) with doc_id={doc_id}"
        )
        return doc_id

    def insert_section(
        self,
        doc_id,
        node_id,
        title,
        summary,
        text_content,
        start_index,
        end_index,
        depth_level,
    ):
        """Insert a section vertex and return its section_id."""
        title = (title or "")[:4000]
        sql = """
            INSERT INTO sections
                (doc_id, node_id, title, summary, text_content,
                 start_index, end_index, depth_level)
            VALUES
                (:doc_id, :node_id, :title, :summary, :text_content,
                 :start_index, :end_index, :depth_level)
            RETURNING section_id INTO :out_id
        """
        section_id = self.db.execute_returning(
            sql,
            {
                "doc_id": doc_id,
                "node_id": node_id,
                "title": title,
                "summary": summary,
                "text_content": text_content,
                "start_index": start_index,
                "end_index": end_index,
                "depth_level": depth_level,
            },
            returning_col="id",
        )
        logger.info(f"Inserted section '{title}' with section_id={section_id}")
        return section_id

    def upsert_entity(self, name, entity_type, description):
        """Insert an entity or return the id of an existing one (by name + type)."""
        existing = self.db.fetchone(
            "SELECT entity_id FROM entities WHERE name = :name AND entity_type = :entity_type",
            {"name": name, "entity_type": entity_type},
        )
        if existing:
            logger.debug(f"Entity '{name}' already exists with id={existing['entity_id']}")
            return existing["entity_id"]

        sql = """
            INSERT INTO entities (name, entity_type, description)
            VALUES (:name, :entity_type, :description)
            RETURNING entity_id INTO :out_id
        """
        entity_id = self.db.execute_returning(
            sql,
            {
                "name": name,
                "entity_type": entity_type,
                "description": description,
            },
            returning_col="id",
        )
        logger.info(f"Inserted entity '{name}' ({entity_type}) with entity_id={entity_id}")
        return entity_id

    def insert_hierarchy_edge(self, parent_id, child_id):
        """Create a parent_of edge between two sections."""
        sql = """
            INSERT INTO section_hierarchy (parent_id, child_id)
            VALUES (:parent_id, :child_id)
        """
        self.db.execute(sql, {"parent_id": parent_id, "child_id": child_id})
        logger.debug(f"Hierarchy edge: section {parent_id} -> section {child_id}")

    def insert_mention_edge(self, section_id, entity_id, relevance="MENTIONS"):
        """Create a mentions edge between a section and an entity."""
        sql = """
            INSERT INTO section_entities (section_id, entity_id, relevance)
            VALUES (:section_id, :entity_id, :relevance)
        """
        self.db.execute(
            sql,
            {"section_id": section_id, "entity_id": entity_id, "relevance": relevance},
        )
        logger.debug(f"Mention edge: section {section_id} -> entity {entity_id} ({relevance})")

    def insert_entity_relationship(self, source_id, target_id, relationship="RELATED_TO"):
        """Create a related_to edge between two entities."""
        sql = """
            INSERT INTO entity_relationships (source_entity, target_entity, relationship)
            VALUES (:source_id, :target_id, :relationship)
        """
        self.db.execute(
            sql,
            {"source_id": source_id, "target_id": target_id, "relationship": relationship},
        )
        logger.debug(f"Entity relationship: {source_id} -[{relationship}]-> {target_id}")

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def get_all_documents(self):
        """Return all documents as a list of dicts."""
        return self.db.fetchall("SELECT * FROM documents ORDER BY doc_id")

    def get_document_sections(self, doc_id):
        """Return all sections belonging to a document."""
        return self.db.fetchall(
            "SELECT * FROM sections WHERE doc_id = :doc_id ORDER BY start_index",
            {"doc_id": doc_id},
        )

    def get_section_children(self, section_id):
        """Return child sections via the section_hierarchy edge table."""
        sql = """
            SELECT s.*
            FROM sections s
            JOIN section_hierarchy h ON h.child_id = s.section_id
            WHERE h.parent_id = :section_id
            ORDER BY s.start_index
        """
        return self.db.fetchall(sql, {"section_id": section_id})

    def get_section_entities(self, section_id):
        """Return entities mentioned in a section with relevance info."""
        sql = """
            SELECT e.entity_id, e.name, e.entity_type, e.description, se.relevance
            FROM entities e
            JOIN section_entities se ON se.entity_id = e.entity_id
            WHERE se.section_id = :section_id
            ORDER BY e.name
        """
        return self.db.fetchall(sql, {"section_id": section_id})

    def get_all_entities(self):
        """Return all entities as a list of dicts."""
        return self.db.fetchall("SELECT * FROM entities ORDER BY entity_id")

    # ------------------------------------------------------------------
    # Entity resolution methods
    # ------------------------------------------------------------------

    def find_similar_entities(self, embedding, entity_type, threshold, exclude_id=None):
        """Find entities with similar name embeddings using VECTOR_DISTANCE."""
        sql = """
            SELECT entity_id, name, entity_type,
                   VECTOR_DISTANCE(name_embedding, :embedding, COSINE) AS distance
            FROM entities
            WHERE entity_type = :entity_type
              AND name_embedding IS NOT NULL
              AND entity_id != :exclude_id
              AND VECTOR_DISTANCE(name_embedding, :embedding, COSINE) < :threshold
            ORDER BY distance
            FETCH FIRST 5 ROWS ONLY
        """
        return self.db.fetchall(sql, {
            "embedding": embedding,
            "entity_type": entity_type,
            "exclude_id": exclude_id or -1,
            "threshold": threshold,
        })

    def insert_entity_alias(self, canonical_id, alias_id, similarity, confirmed=0):
        """Create an alias_of edge between two entities."""
        sql = """
            INSERT INTO entity_aliases (canonical_id, alias_id, similarity, confirmed)
            VALUES (:canonical_id, :alias_id, :similarity, :confirmed)
        """
        self.db.execute(sql, {
            "canonical_id": canonical_id,
            "alias_id": alias_id,
            "similarity": similarity,
            "confirmed": confirmed,
        })

    def update_entity_canonical(self, entity_id, canonical_id):
        """Set the canonical_id for an entity (marks it as an alias)."""
        sql = "UPDATE entities SET canonical_id = :canonical_id WHERE entity_id = :entity_id"
        self.db.execute(sql, {"canonical_id": canonical_id, "entity_id": entity_id})

    def update_entity_embedding(self, entity_id, embedding):
        """Store the name embedding vector for an entity."""
        sql = "UPDATE entities SET name_embedding = :embedding WHERE entity_id = :entity_id"
        self.db.execute(sql, {"embedding": embedding, "entity_id": entity_id})

    def get_entity_sections(self, entity_name):
        """Return all sections that mention an entity (by entity name), with document info.

        Uses case-insensitive matching with LIKE for better recall.
        """
        sql = """
            SELECT s.section_id, s.title, s.summary, s.text_content,
                   s.depth_level, se.relevance, s.start_index,
                   d.doc_id, d.doc_name
            FROM sections s
            JOIN section_entities se ON se.section_id = s.section_id
            JOIN entities e ON e.entity_id = se.entity_id
            JOIN documents d ON d.doc_id = s.doc_id
            WHERE LOWER(e.name) LIKE '%' || LOWER(:entity_name) || '%'
              AND ROWNUM <= 10
            ORDER BY s.start_index
        """
        return self.db.fetchall(sql, {"entity_name": entity_name})

    def get_related_entities(self, entity_name):
        """Return entities related to the given entity (by name).

        Uses case-insensitive matching with LIKE for better recall.
        """
        sql = """
            SELECT e2.entity_id, e2.name, e2.entity_type, e2.description,
                   er.relationship
            FROM entities e1
            JOIN entity_relationships er ON er.source_entity = e1.entity_id
            JOIN entities e2 ON e2.entity_id = er.target_entity
            WHERE LOWER(e1.name) LIKE '%' || LOWER(:entity_name) || '%'
            ORDER BY e2.name
            FETCH FIRST 20 ROWS ONLY
        """
        return self.db.fetchall(sql, {"entity_name": entity_name})

    def get_full_graph_data(self):
        """Build a full graph structure for D3.js visualization.

        Returns:
            dict with "nodes" and "edges" lists.
            Nodes: {"id": "doc_1", "type": "document", "label": "..."}
            Edges: {"source": "...", "target": "...", "type": "..."}
        """
        nodes = []
        edges = []

        # Document nodes
        for doc in self.db.fetchall(
            "SELECT doc_id, doc_name, doc_group, doc_version FROM documents"
        ):
            node = {
                "id": f"doc_{doc['doc_id']}",
                "type": "document",
                "label": doc["doc_name"],
            }
            if doc.get("doc_group"):
                node["doc_group"] = doc["doc_group"]
                node["doc_version"] = doc.get("doc_version", 1)
            nodes.append(node)

        # Section nodes
        for sec in self.db.fetchall("SELECT section_id, title, doc_id FROM sections"):
            nodes.append({
                "id": f"sec_{sec['section_id']}",
                "type": "section",
                "label": sec["title"] or f"Section {sec['section_id']}",
            })
            # Implicit doc -> section edge
            edges.append({
                "source": f"doc_{sec['doc_id']}",
                "target": f"sec_{sec['section_id']}",
                "type": "contains",
            })

        # Entity nodes
        for ent in self.db.fetchall("SELECT entity_id, name, entity_type FROM entities"):
            nodes.append({
                "id": f"ent_{ent['entity_id']}",
                "type": "entity",
                "label": ent["name"],
            })

        # Hierarchy edges
        for h in self.db.fetchall("SELECT parent_id, child_id FROM section_hierarchy"):
            edges.append({
                "source": f"sec_{h['parent_id']}",
                "target": f"sec_{h['child_id']}",
                "type": "parent_of",
            })

        # Mention edges
        for m in self.db.fetchall(
            "SELECT section_id, entity_id, relevance FROM section_entities"
        ):
            edges.append({
                "source": f"sec_{m['section_id']}",
                "target": f"ent_{m['entity_id']}",
                "type": m["relevance"].lower() if m["relevance"] else "mentions",
            })

        # Entity relationship edges
        for r in self.db.fetchall(
            "SELECT source_entity, target_entity, relationship FROM entity_relationships"
        ):
            edges.append({
                "source": f"ent_{r['source_entity']}",
                "target": f"ent_{r['target_entity']}",
                "type": r["relationship"].lower() if r["relationship"] else "related_to",
            })

        return {"nodes": nodes, "edges": edges}

    def get_versioned_graph_data(self, doc_group, version):
        """Return graph data with temporal annotations for a specific version.

        Fetches the full graph and then overlays temporal change information
        (APPEARED, DISAPPEARED, MODIFIED, STABLE) on entity nodes that have
        recorded changes for the given doc_group and version.
        """
        data = self.get_full_graph_data()
        try:
            changes = self.get_temporal_changes(doc_group, None, version)
            change_map = {}
            for c in changes:
                entity_name = c.get("name") or c.get("entity_name")
                if entity_name:
                    change_map[entity_name] = c["change_type"]
            for node in data.get("nodes", []):
                if node.get("type") == "entity" and node.get("label") in change_map:
                    node["temporal_status"] = change_map[node["label"]]
        except Exception:
            pass  # temporal data may not exist yet
        return data

    # ------------------------------------------------------------------
    # SQL/PGQ graph query methods
    # ------------------------------------------------------------------

    def graph_query_entity_sections(self, entity_name):
        """Use GRAPH_TABLE with MATCH to find sections mentioning an entity.

        MATCH pattern: (s:section) -[m:mentions]-> (e:entity)
        """
        sql = """
            SELECT *
            FROM GRAPH_TABLE (doc_knowledge_graph
                MATCH (s IS section) -[m IS mentions]-> (e IS entity)
                WHERE e.name = :entity_name
                COLUMNS (
                    s.section_id,
                    s.title AS section_title,
                    s.depth_level,
                    m.relevance,
                    e.name AS entity_name,
                    e.entity_type
                )
            )
            ORDER BY section_id
        """
        return self.db.fetchall(sql, {"entity_name": entity_name})

    def graph_query_related_entities(self, entity_name):
        """Use GRAPH_TABLE with MATCH to find entities related to a given entity.

        MATCH pattern: (e1:entity) -[r:related_to]-> (e2:entity)
        """
        sql = """
            SELECT *
            FROM GRAPH_TABLE (doc_knowledge_graph
                MATCH (e1 IS entity) -[r IS related_to]-> (e2 IS entity)
                WHERE e1.name = :entity_name
                COLUMNS (
                    e1.name AS source_name,
                    r.relationship,
                    e2.entity_id AS related_id,
                    e2.name AS related_name,
                    e2.entity_type AS related_type
                )
            )
            ORDER BY related_name
        """
        return self.db.fetchall(sql, {"entity_name": entity_name})

    def graph_query_section_children(self, section_title):
        """Find all descendants of a section using hierarchical CONNECT BY.

        Uses Oracle's CONNECT BY PRIOR for recursive traversal through the
        section_hierarchy edge table (parent_of edges in the property graph).
        """
        sql = """
            SELECT s.section_id AS child_section_id,
                   s.title       AS child_title,
                   s.depth_level AS child_depth,
                   LEVEL         AS tree_level
            FROM   section_hierarchy h
            JOIN   sections s ON s.section_id = h.child_id
            START WITH h.parent_id = (
                SELECT section_id FROM sections
                WHERE title = :section_title
                FETCH FIRST 1 ROWS ONLY
            )
            CONNECT BY PRIOR h.child_id = h.parent_id
            ORDER BY s.depth_level, s.section_id
        """
        return self.db.fetchall(sql, {"section_title": section_title})

    # ------------------------------------------------------------------
    # Multi-hop GRAPH_TABLE traversal methods
    # ------------------------------------------------------------------

    def traverse_entity_neighborhood(self, entity_id: int) -> dict:
        """Find all sections mentioning an entity and co-mentioned entities in those sections.

        Uses GRAPH_TABLE MATCH to traverse: entity <- mentions - section - mentions -> entity.
        Deduplicates sections and entities from the flat row set.
        """
        sql = """
            SELECT s.section_id, s.title, s.text_content, s.depth_level,
                   m.relevance,
                   e2.entity_id AS co_entity_id, e2.name AS co_entity_name,
                   e2.entity_type AS co_entity_type
            FROM GRAPH_TABLE (doc_knowledge_graph
                MATCH (e1 IS entity WHERE e1.entity_id = :entity_id)
                      <-[m IS mentions]- (s IS section)
                      -[m2 IS mentions]-> (e2 IS entity)
                COLUMNS (
                    s.section_id, s.title, s.text_content, s.depth_level,
                    m.relevance,
                    e2.entity_id AS co_entity_id, e2.name AS co_entity_name,
                    e2.entity_type AS co_entity_type
                )
            )
            WHERE co_entity_id != :entity_id
        """
        params = {"entity_id": entity_id}
        t0 = time.perf_counter()
        rows = self.db.fetchall(sql, params)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        # Deduplicate sections by section_id
        seen_sections = {}
        for row in rows:
            sid = row["section_id"]
            if sid not in seen_sections:
                seen_sections[sid] = {
                    "section_id": sid,
                    "title": row["title"],
                    "text_content": row["text_content"],
                    "depth_level": row["depth_level"],
                    "relevance": row["relevance"],
                }

        # Deduplicate entities by entity_id
        seen_entities = {}
        for row in rows:
            eid = row["co_entity_id"]
            if eid not in seen_entities:
                seen_entities[eid] = {
                    "entity_id": eid,
                    "name": row["co_entity_name"],
                    "entity_type": row["co_entity_type"],
                }

        gq = GraphQuery(
            sql=sql,
            params=params,
            purpose="Find sections mentioning entity and co-mentioned entities",
            rows_returned=len(rows),
            execution_ms=elapsed_ms,
        )
        return {
            "sections": list(seen_sections.values()),
            "entities": list(seen_entities.values()),
            "graph_query": gq,
        }

    def traverse_section_ancestors(self, section_id: int) -> list[dict]:
        """Find all ancestors of a section using recursive CONNECT BY traversal.

        Returns ancestors ordered from root (topmost) down to the immediate parent.
        """
        sql = """
            SELECT s.section_id, s.title, s.depth_level, LEVEL AS tree_level
            FROM section_hierarchy h
            JOIN sections s ON s.section_id = h.parent_id
            START WITH h.child_id = :section_id
            CONNECT BY PRIOR h.parent_id = h.child_id
            ORDER BY LEVEL DESC
        """
        params = {"section_id": section_id}
        t0 = time.perf_counter()
        rows = self.db.fetchall(sql, params)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.debug(
            f"traverse_section_ancestors({section_id}): {len(rows)} ancestors in {elapsed_ms:.1f}ms"
        )
        return rows

    def traverse_section_descendants(self, section_id: int) -> list[dict]:
        """Find all descendants of a section using recursive CONNECT BY traversal.

        Returns descendants ordered by tree level then section_id.
        """
        sql = """
            SELECT s.section_id, s.title, s.depth_level, LEVEL AS tree_level
            FROM section_hierarchy h
            JOIN sections s ON s.section_id = h.child_id
            START WITH h.parent_id = :section_id
            CONNECT BY PRIOR h.child_id = h.parent_id
            ORDER BY LEVEL, s.section_id
        """
        params = {"section_id": section_id}
        t0 = time.perf_counter()
        rows = self.db.fetchall(sql, params)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.debug(
            f"traverse_section_descendants({section_id}): {len(rows)} descendants in {elapsed_ms:.1f}ms"
        )
        return rows

    def find_entity_paths(self, source_name: str, target_name: str, max_hops: int = 2) -> dict:
        """Find paths between two entities through intermediate entities (2-hop).

        Uses GRAPH_TABLE MATCH to traverse: source -[r1]-> mid -[r2]-> target.
        """
        sql = """
            SELECT e1.name AS source_name,
                   mid.entity_id AS mid_id, mid.name AS mid_name, mid.entity_type AS mid_type,
                   r1.relationship AS r1_type,
                   e2.name AS target_name,
                   r2.relationship AS r2_type
            FROM GRAPH_TABLE (doc_knowledge_graph
                MATCH (e1 IS entity WHERE LOWER(e1.name) LIKE '%' || LOWER(:source_name) || '%')
                      -[r1 IS related_to]-> (mid IS entity)
                      -[r2 IS related_to]-> (e2 IS entity WHERE LOWER(e2.name) LIKE '%' || LOWER(:target_name) || '%')
                COLUMNS (
                    e1.name, mid.entity_id, mid.name, mid.entity_type,
                    r1.relationship, e2.name, r2.relationship
                )
            )
            FETCH FIRST 10 ROWS ONLY
        """
        params = {"source_name": source_name, "target_name": target_name}
        t0 = time.perf_counter()
        rows = self.db.fetchall(sql, params)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        gq = GraphQuery(
            sql=sql,
            params=params,
            purpose=f"Find paths from '{source_name}' to '{target_name}' via intermediate entities",
            rows_returned=len(rows),
            execution_ms=elapsed_ms,
        )
        return {"paths": rows, "graph_query": gq}

    def get_multi_hop_entities(self, entity_id: int, max_hops: int = 2) -> dict:
        """N-hop entity expansion via GRAPH_TABLE MATCH.

        Gets all entities within N relationship hops of the given entity.
        For max_hops=1, uses a single-hop query. For max_hops>=2, UNIONs
        1-hop and 2-hop results.
        """
        sql_1hop = """
            SELECT e2.entity_id, e2.name, e2.entity_type, r.relationship, 1 AS hops
            FROM GRAPH_TABLE (doc_knowledge_graph
                MATCH (e1 IS entity WHERE e1.entity_id = :entity_id)
                      -[r IS related_to]-> (e2 IS entity)
                COLUMNS (e2.entity_id, e2.name, e2.entity_type, r.relationship)
            )
        """

        if max_hops >= 2:
            sql_2hop = """
            UNION
            SELECT e3.entity_id, e3.name, e3.entity_type, r2.relationship, 2 AS hops
            FROM GRAPH_TABLE (doc_knowledge_graph
                MATCH (e1 IS entity WHERE e1.entity_id = :entity_id)
                      -[r1 IS related_to]-> (mid IS entity)
                      -[r2 IS related_to]-> (e3 IS entity)
                COLUMNS (e3.entity_id, e3.name, e3.entity_type, r2.relationship)
            )
            WHERE e3.entity_id != :entity_id
            """
            sql = sql_1hop + sql_2hop
        else:
            sql = sql_1hop

        params = {"entity_id": entity_id}
        t0 = time.perf_counter()
        rows = self.db.fetchall(sql, params)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        gq = GraphQuery(
            sql=sql,
            params=params,
            purpose=f"Find entities within {max_hops} hops of entity {entity_id}",
            rows_returned=len(rows),
            execution_ms=elapsed_ms,
        )
        return {"entities": rows, "graph_query": gq}

    # ------------------------------------------------------------------
    # Enrichment support methods
    # ------------------------------------------------------------------

    def get_isolated_entities(self, min_mentions=2):
        """Find entities mentioned frequently but with no relationship edges."""
        sql = """
            SELECT e.entity_id, e.name, e.entity_type, COUNT(se.edge_id) AS mention_count
            FROM entities e
            JOIN section_entities se ON se.entity_id = e.entity_id
            LEFT JOIN entity_relationships er
                ON er.source_entity = e.entity_id OR er.target_entity = e.entity_id
            WHERE er.edge_id IS NULL
            GROUP BY e.entity_id, e.name, e.entity_type
            HAVING COUNT(se.edge_id) >= :min_mentions
            ORDER BY COUNT(se.edge_id) DESC
        """
        return self.db.fetchall(sql, {"min_mentions": min_mentions})

    def get_cooccurring_pairs(self, min_shared=2):
        """Find entity pairs sharing sections but lacking relationship edges."""
        sql = """
            SELECT e1.entity_id AS entity1_id, e1.name AS entity1_name, e1.entity_type AS entity1_type,
                   e2.entity_id AS entity2_id, e2.name AS entity2_name, e2.entity_type AS entity2_type,
                   COUNT(DISTINCT se1.section_id) AS shared_sections
            FROM section_entities se1
            JOIN section_entities se2
                ON se1.section_id = se2.section_id AND se1.entity_id < se2.entity_id
            JOIN entities e1 ON e1.entity_id = se1.entity_id
            JOIN entities e2 ON e2.entity_id = se2.entity_id
            LEFT JOIN entity_relationships er
                ON (er.source_entity = se1.entity_id AND er.target_entity = se2.entity_id)
                OR (er.source_entity = se2.entity_id AND er.target_entity = se1.entity_id)
            WHERE er.edge_id IS NULL
            GROUP BY e1.entity_id, e1.name, e1.entity_type,
                     e2.entity_id, e2.name, e2.entity_type
            HAVING COUNT(DISTINCT se1.section_id) >= :min_shared
            ORDER BY COUNT(DISTINCT se1.section_id) DESC
        """
        return self.db.fetchall(sql, {"min_shared": min_shared})

    def get_shared_section_text(self, entity1_id, entity2_id):
        """Get concatenated text of sections where both entities appear."""
        sql = """
            SELECT s.text_content
            FROM sections s
            JOIN section_entities se1 ON se1.section_id = s.section_id AND se1.entity_id = :e1
            JOIN section_entities se2 ON se2.section_id = s.section_id AND se2.entity_id = :e2
            FETCH FIRST 3 ROWS ONLY
        """
        rows = self.db.fetchall(sql, {"e1": entity1_id, "e2": entity2_id})
        return "\n\n".join(r.get("text_content", "") for r in rows if r.get("text_content"))

    def insert_enriched_relationship(self, source_id, target_id, relationship, confidence=0.8):
        """Insert a relationship edge marked as enrichment-generated."""
        sql = """
            INSERT INTO entity_relationships
                (source_entity, target_entity, relationship, edge_source, confidence)
            VALUES (:source_id, :target_id, :relationship, 'ENRICHMENT', :confidence)
        """
        self.db.execute(sql, {
            "source_id": source_id, "target_id": target_id,
            "relationship": relationship, "confidence": confidence,
        })

    # ------------------------------------------------------------------
    # Temporal versioning methods
    # ------------------------------------------------------------------

    def get_previous_version(self, doc_group, current_version):
        """Get the document record for the version before current_version in a group."""
        sql = """
            SELECT doc_id, doc_name, doc_version
            FROM documents
            WHERE doc_group = :doc_group AND doc_version = :prev_version
        """
        return self.db.fetchone(sql, {"doc_group": doc_group, "prev_version": current_version - 1})

    def get_doc_entities(self, doc_id):
        """Get all entities mentioned in a document's sections."""
        sql = """
            SELECT DISTINCT e.entity_id, e.name, e.entity_type
            FROM entities e
            JOIN section_entities se ON se.entity_id = e.entity_id
            JOIN sections s ON s.section_id = se.section_id
            WHERE s.doc_id = :doc_id
            ORDER BY e.name
        """
        return self.db.fetchall(sql, {"doc_id": doc_id})

    def insert_temporal_edge(self, source_doc_id, target_doc_id, entity_id,
                             change_type, old_value=None, new_value=None, confidence=1.0):
        """Create a temporal change edge between two document versions."""
        sql = """
            INSERT INTO temporal_edges
                (source_doc_id, target_doc_id, entity_id, change_type, old_value, new_value, confidence)
            VALUES (:src, :tgt, :eid, :change_type, :old_value, :new_value, :confidence)
        """
        self.db.execute(sql, {
            "src": source_doc_id, "tgt": target_doc_id, "eid": entity_id,
            "change_type": change_type, "old_value": old_value,
            "new_value": new_value, "confidence": confidence,
        })

    def get_temporal_changes(self, doc_group, version_from, version_to):
        """Get all temporal changes between two versions of a document group."""
        sql = """
            SELECT te.edge_id, te.entity_id, e.name, e.entity_type,
                   te.change_type, te.old_value, te.new_value, te.confidence
            FROM temporal_edges te
            JOIN documents d1 ON d1.doc_id = te.source_doc_id
            JOIN documents d2 ON d2.doc_id = te.target_doc_id
            LEFT JOIN entities e ON e.entity_id = te.entity_id
            WHERE d1.doc_group = :doc_group
              AND d1.doc_version = :v_from
              AND d2.doc_version = :v_to
            ORDER BY te.change_type, e.name
        """
        return self.db.fetchall(sql, {
            "doc_group": doc_group, "v_from": version_from, "v_to": version_to,
        })

    # ------------------------------------------------------------------
    # Session / conversational memory methods
    # ------------------------------------------------------------------

    def create_session(self, title=None, metadata=None):
        """Create a new conversation session and return its session_id."""
        sql = """
            INSERT INTO sessions (title, metadata)
            VALUES (:title, :metadata)
            RETURNING session_id INTO :out_id
        """
        session_id = self.db.execute_returning(
            sql, {"title": title, "metadata": metadata}, returning_col="id"
        )
        logger.info(f"Created session {session_id}")
        return session_id

    def create_turn(self, session_id, turn_number, question, intent=None):
        """Create a new turn in a session and return its turn_id."""
        sql = """
            INSERT INTO turns (session_id, turn_number, question, intent)
            VALUES (:session_id, :turn_number, :question, :intent)
            RETURNING turn_id INTO :out_id
        """
        return self.db.execute_returning(
            sql,
            {"session_id": session_id, "turn_number": turn_number,
             "question": question, "intent": intent},
            returning_col="id",
        )

    def update_turn_answer(self, turn_id, answer):
        """Store the answer for a completed turn."""
        sql = "UPDATE turns SET answer = :answer WHERE turn_id = :turn_id"
        self.db.execute(sql, {"answer": answer, "turn_id": turn_id})

    def insert_turn_entity(self, turn_id, entity_id, role="REFERENCED"):
        """Record that a turn touched an entity."""
        sql = """
            INSERT INTO turn_entities (turn_id, entity_id, role)
            VALUES (:turn_id, :entity_id, :role)
        """
        self.db.execute(sql, {"turn_id": turn_id, "entity_id": entity_id, "role": role})

    def insert_turn_section(self, turn_id, section_id, rank_score=None):
        """Record that a turn used a section for context."""
        sql = """
            INSERT INTO turn_sections (turn_id, section_id, rank_score)
            VALUES (:turn_id, :section_id, :rank_score)
        """
        self.db.execute(sql, {"turn_id": turn_id, "section_id": section_id, "rank_score": rank_score})

    def get_session_context(self, session_id):
        """Get the context from the most recent turn in a session.

        Returns dict with primary_entities and previous_sections.
        """
        # Get latest turn number
        latest = self.db.fetchone(
            "SELECT MAX(turn_number) AS turn_number FROM turns WHERE session_id = :sid",
            {"sid": session_id},
        )
        if not latest or latest.get("turn_number") is None:
            return {"primary_entities": [], "previous_sections": []}

        latest_turn = self.db.fetchone(
            "SELECT turn_id FROM turns WHERE session_id = :sid AND turn_number = :tn",
            {"sid": session_id, "tn": latest["turn_number"]},
        )
        if not latest_turn:
            return {"primary_entities": [], "previous_sections": []}

        turn_id = latest_turn["turn_id"]

        # Get entities from that turn
        entities = self.db.fetchall(
            """SELECT e.entity_id, e.name, e.entity_type, te.role
               FROM turn_entities te
               JOIN entities e ON e.entity_id = te.entity_id
               WHERE te.turn_id = :tid
               ORDER BY te.role, e.name""",
            {"tid": turn_id},
        )

        # Get sections from that turn
        sections = self.db.fetchall(
            "SELECT section_id, rank_score FROM turn_sections WHERE turn_id = :tid ORDER BY rank_score DESC",
            {"tid": turn_id},
        )

        return {
            "primary_entities": entities,
            "previous_sections": [s["section_id"] for s in sections],
        }

    def list_sessions(self):
        """Return all conversation sessions."""
        return self.db.fetchall("SELECT * FROM sessions ORDER BY started_at DESC")

    def get_session_turns(self, session_id):
        """Return all turns in a session with their entities."""
        return self.db.fetchall(
            "SELECT * FROM turns WHERE session_id = :sid ORDER BY turn_number",
            {"sid": session_id},
        )
