-- OraclePageIndex Schema for Oracle 26ai Free
-- Run as: sqlplus pageindex/pageindex@localhost:1521/FREEPDB1 @setup_schema.sql

-- Drop existing objects (idempotent)
BEGIN
    EXECUTE IMMEDIATE 'DROP PROPERTY GRAPH doc_knowledge_graph';
EXCEPTION WHEN OTHERS THEN NULL;
END;
/

BEGIN
    FOR t IN (SELECT table_name FROM user_tables WHERE table_name IN (
        'ENTITY_RELATIONSHIPS', 'SECTION_ENTITIES', 'SECTION_HIERARCHY',
        'ENTITIES', 'SECTIONS', 'DOCUMENTS'
    )) LOOP
        EXECUTE IMMEDIATE 'DROP TABLE ' || t.table_name || ' CASCADE CONSTRAINTS';
    END LOOP;
END;
/

-- Vertex tables
CREATE TABLE documents (
    doc_id          NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    doc_name        VARCHAR2(500) NOT NULL,
    doc_description CLOB,
    source_path     VARCHAR2(1000),
    created_at      TIMESTAMP DEFAULT SYSTIMESTAMP
);

CREATE TABLE sections (
    section_id    NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    doc_id        NUMBER NOT NULL REFERENCES documents(doc_id),
    node_id       VARCHAR2(10),
    title         VARCHAR2(4000),
    summary       CLOB,
    text_content  CLOB,
    start_index   NUMBER,
    end_index     NUMBER,
    depth_level   NUMBER DEFAULT 0
);

CREATE TABLE entities (
    entity_id     NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name          VARCHAR2(500) NOT NULL,
    entity_type   VARCHAR2(100),
    description   CLOB,
    CONSTRAINT uq_entity UNIQUE (name, entity_type)
);

-- Edge tables
CREATE TABLE section_hierarchy (
    edge_id       NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    parent_id     NUMBER NOT NULL REFERENCES sections(section_id),
    child_id      NUMBER NOT NULL REFERENCES sections(section_id)
);

CREATE TABLE section_entities (
    edge_id       NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    section_id    NUMBER NOT NULL REFERENCES sections(section_id),
    entity_id     NUMBER NOT NULL REFERENCES entities(entity_id),
    relevance     VARCHAR2(20) DEFAULT 'MENTIONS'
);

CREATE TABLE entity_relationships (
    edge_id       NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_entity NUMBER NOT NULL REFERENCES entities(entity_id),
    target_entity NUMBER NOT NULL REFERENCES entities(entity_id),
    relationship  VARCHAR2(100) DEFAULT 'RELATED_TO'
);

-- Indexes for performance
CREATE INDEX idx_sections_doc_id ON sections(doc_id);
CREATE INDEX idx_section_hierarchy_parent ON section_hierarchy(parent_id);
CREATE INDEX idx_section_hierarchy_child ON section_hierarchy(child_id);
CREATE INDEX idx_section_entities_section ON section_entities(section_id);
CREATE INDEX idx_section_entities_entity ON section_entities(entity_id);
CREATE INDEX idx_entity_rel_source ON entity_relationships(source_entity);
CREATE INDEX idx_entity_rel_target ON entity_relationships(target_entity);

-- Property Graph
CREATE PROPERTY GRAPH doc_knowledge_graph
    VERTEX TABLES (
        documents
            KEY (doc_id)
            LABEL document
            PROPERTIES ALL COLUMNS,
        sections
            KEY (section_id)
            LABEL section
            PROPERTIES ALL COLUMNS,
        entities
            KEY (entity_id)
            LABEL entity
            PROPERTIES ALL COLUMNS
    )
    EDGE TABLES (
        section_hierarchy
            KEY (edge_id)
            SOURCE KEY (parent_id) REFERENCES sections (section_id)
            DESTINATION KEY (child_id) REFERENCES sections (section_id)
            LABEL parent_of
            PROPERTIES ALL COLUMNS,
        section_entities
            KEY (edge_id)
            SOURCE KEY (section_id) REFERENCES sections (section_id)
            DESTINATION KEY (entity_id) REFERENCES entities (entity_id)
            LABEL mentions
            PROPERTIES ALL COLUMNS,
        entity_relationships
            KEY (edge_id)
            SOURCE KEY (source_entity) REFERENCES entities (entity_id)
            DESTINATION KEY (target_entity) REFERENCES entities (entity_id)
            LABEL related_to
            PROPERTIES ALL COLUMNS
    );

COMMIT;
