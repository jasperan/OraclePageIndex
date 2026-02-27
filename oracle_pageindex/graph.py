import logging

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

    def insert_document(self, doc_name, doc_description, source_path):
        """Insert a document vertex and return its doc_id."""
        sql = """
            INSERT INTO documents (doc_name, doc_description, source_path)
            VALUES (:doc_name, :doc_description, :source_path)
            RETURNING doc_id INTO :out_id
        """
        doc_id = self.db.execute_returning(
            sql,
            {
                "doc_name": doc_name,
                "doc_description": doc_description,
                "source_path": source_path,
            },
            returning_col="id",
        )
        logger.info(f"Inserted document '{doc_name}' with doc_id={doc_id}")
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

    def get_entity_sections(self, entity_name):
        """Return all sections that mention an entity (by entity name), with document info."""
        sql = """
            SELECT s.section_id, s.title, s.depth_level, se.relevance,
                   d.doc_id, d.doc_name
            FROM sections s
            JOIN section_entities se ON se.section_id = s.section_id
            JOIN entities e ON e.entity_id = se.entity_id
            JOIN documents d ON d.doc_id = s.doc_id
            WHERE e.name = :entity_name
            ORDER BY d.doc_name, s.start_index
        """
        return self.db.fetchall(sql, {"entity_name": entity_name})

    def get_related_entities(self, entity_name):
        """Return entities related to the given entity (by name)."""
        sql = """
            SELECT e2.entity_id, e2.name, e2.entity_type, e2.description,
                   er.relationship
            FROM entities e1
            JOIN entity_relationships er ON er.source_entity = e1.entity_id
            JOIN entities e2 ON e2.entity_id = er.target_entity
            WHERE e1.name = :entity_name
            ORDER BY e2.name
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
        for doc in self.db.fetchall("SELECT doc_id, doc_name FROM documents"):
            nodes.append({
                "id": f"doc_{doc['doc_id']}",
                "type": "document",
                "label": doc["doc_name"],
            })

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
        """Use GRAPH_TABLE with recursive MATCH to find all descendants of a section.

        MATCH pattern: (parent) -[parent_of]->+ (child) for transitive closure.
        """
        sql = """
            SELECT *
            FROM GRAPH_TABLE (doc_knowledge_graph
                MATCH (parent IS section) -[IS parent_of]->+ (child IS section)
                WHERE parent.title = :section_title
                COLUMNS (
                    parent.section_id AS parent_section_id,
                    parent.title AS parent_title,
                    child.section_id AS child_section_id,
                    child.title AS child_title,
                    child.depth_level AS child_depth
                )
            )
            ORDER BY child_depth, child_section_id
        """
        return self.db.fetchall(sql, {"section_title": section_title})
