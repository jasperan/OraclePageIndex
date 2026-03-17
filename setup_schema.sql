-- OraclePageIndex Schema for Oracle 26ai Free — Living Graph v2 (5V+8E)
-- Run as: sqlplus pageindex/pageindex@localhost:1521/FREEPDB1 @setup_schema.sql

-- Drop existing objects (idempotent)
BEGIN
    EXECUTE IMMEDIATE 'DROP PROPERTY GRAPH doc_knowledge_graph';
EXCEPTION WHEN OTHERS THEN NULL;
END;
/

-- Drop edge tables first (depend on vertex tables), then vertex tables
-- New edge tables
BEGIN EXECUTE IMMEDIATE 'DROP TABLE entity_aliases CASCADE CONSTRAINTS'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP TABLE temporal_edges CASCADE CONSTRAINTS'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP TABLE turn_sections CASCADE CONSTRAINTS'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP TABLE turn_entities CASCADE CONSTRAINTS'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
-- Original edge tables
BEGIN EXECUTE IMMEDIATE 'DROP TABLE entity_relationships CASCADE CONSTRAINTS'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP TABLE section_entities CASCADE CONSTRAINTS'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP TABLE section_hierarchy CASCADE CONSTRAINTS'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
-- New vertex tables
BEGIN EXECUTE IMMEDIATE 'DROP TABLE turns CASCADE CONSTRAINTS'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP TABLE sessions CASCADE CONSTRAINTS'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
-- Original vertex tables
BEGIN EXECUTE IMMEDIATE 'DROP TABLE entities CASCADE CONSTRAINTS'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP TABLE sections CASCADE CONSTRAINTS'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP TABLE documents CASCADE CONSTRAINTS'; EXCEPTION WHEN OTHERS THEN NULL; END;
/

-- ============================================================
-- Vertex tables
-- ============================================================

CREATE TABLE documents (
    doc_id          NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    doc_name        VARCHAR2(500) NOT NULL,
    doc_description CLOB,
    source_path     VARCHAR2(1000),
    created_at      TIMESTAMP DEFAULT SYSTIMESTAMP,
    doc_version     NUMBER DEFAULT 1,
    doc_group       VARCHAR2(500)
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
    entity_id       NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name            VARCHAR2(500) NOT NULL,
    entity_type     VARCHAR2(100),
    description     CLOB,
    name_embedding  VECTOR(384, FLOAT32),
    canonical_id    NUMBER REFERENCES entities(entity_id),
    first_seen_doc  NUMBER REFERENCES documents(doc_id),
    last_seen_doc   NUMBER REFERENCES documents(doc_id),
    CONSTRAINT uq_entity UNIQUE (name, entity_type)
);

CREATE TABLE sessions (
    session_id   NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    started_at   TIMESTAMP DEFAULT SYSTIMESTAMP,
    title        VARCHAR2(500),
    metadata     CLOB
);

CREATE TABLE turns (
    turn_id      NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id   NUMBER NOT NULL REFERENCES sessions(session_id),
    turn_number  NUMBER NOT NULL,
    question     CLOB NOT NULL,
    answer       CLOB,
    intent       VARCHAR2(50),
    created_at   TIMESTAMP DEFAULT SYSTIMESTAMP
);

-- ============================================================
-- Edge tables
-- ============================================================

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
    edge_id         NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_entity   NUMBER NOT NULL REFERENCES entities(entity_id),
    target_entity   NUMBER NOT NULL REFERENCES entities(entity_id),
    relationship    VARCHAR2(100) DEFAULT 'RELATED_TO',
    edge_source     VARCHAR2(20) DEFAULT 'EXTRACTION',
    confidence      NUMBER(3,2) DEFAULT 1.0
);

CREATE TABLE turn_entities (
    edge_id    NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    turn_id    NUMBER NOT NULL REFERENCES turns(turn_id),
    entity_id  NUMBER NOT NULL REFERENCES entities(entity_id),
    role       VARCHAR2(20) DEFAULT 'REFERENCED'
);

CREATE TABLE turn_sections (
    edge_id      NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    turn_id      NUMBER NOT NULL REFERENCES turns(turn_id),
    section_id   NUMBER NOT NULL REFERENCES sections(section_id),
    rank_score   NUMBER
);

CREATE TABLE temporal_edges (
    edge_id         NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_doc_id   NUMBER NOT NULL REFERENCES documents(doc_id),
    target_doc_id   NUMBER NOT NULL REFERENCES documents(doc_id),
    entity_id       NUMBER REFERENCES entities(entity_id),
    change_type     VARCHAR2(50) NOT NULL,
    old_value       CLOB,
    new_value       CLOB,
    confidence      NUMBER(3,2) DEFAULT 1.0
);

CREATE TABLE entity_aliases (
    edge_id       NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    canonical_id  NUMBER NOT NULL REFERENCES entities(entity_id),
    alias_id      NUMBER NOT NULL REFERENCES entities(entity_id),
    similarity    NUMBER(5,4),
    confirmed     NUMBER(1) DEFAULT 0
);

-- ============================================================
-- Indexes for performance
-- ============================================================

-- Original indexes
CREATE INDEX idx_sections_doc_id ON sections(doc_id);
CREATE INDEX idx_entities_name ON entities(LOWER(name));
CREATE INDEX idx_section_hierarchy_parent ON section_hierarchy(parent_id);
CREATE INDEX idx_section_hierarchy_child ON section_hierarchy(child_id);
CREATE INDEX idx_section_entities_section ON section_entities(section_id);
CREATE INDEX idx_section_entities_entity ON section_entities(entity_id);
CREATE INDEX idx_entity_rel_source ON entity_relationships(source_entity);
CREATE INDEX idx_entity_rel_target ON entity_relationships(target_entity);

-- New indexes
CREATE INDEX idx_entities_canonical ON entities(canonical_id);
CREATE INDEX idx_turns_session ON turns(session_id);
CREATE INDEX idx_te_turn ON turn_entities(turn_id);
CREATE INDEX idx_te_entity ON turn_entities(entity_id);
CREATE INDEX idx_ts_turn ON turn_sections(turn_id);
CREATE INDEX idx_ts_section ON turn_sections(section_id);
CREATE INDEX idx_temp_source ON temporal_edges(source_doc_id);
CREATE INDEX idx_temp_target ON temporal_edges(target_doc_id);
CREATE INDEX idx_alias_canonical ON entity_aliases(canonical_id);
CREATE INDEX idx_alias_alias ON entity_aliases(alias_id);
CREATE INDEX idx_docs_group ON documents(doc_group);

-- Vector index (Oracle AI Vector Search) — uncomment when confirmed for your Oracle edition
-- CREATE VECTOR INDEX idx_entity_embedding ON entities(name_embedding)
--     ORGANIZATION NEIGHBOR PARTITIONS
--     DISTANCE COSINE;

-- ============================================================
-- Property Graph (5V + 8E)
-- ============================================================

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
            PROPERTIES ALL COLUMNS,
        sessions
            KEY (session_id)
            LABEL session
            PROPERTIES ALL COLUMNS,
        turns
            KEY (turn_id)
            LABEL turn
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
            PROPERTIES ALL COLUMNS,
        turn_entities
            KEY (edge_id)
            SOURCE KEY (turn_id) REFERENCES turns (turn_id)
            DESTINATION KEY (entity_id) REFERENCES entities (entity_id)
            LABEL turn_entity
            PROPERTIES ALL COLUMNS,
        turn_sections
            KEY (edge_id)
            SOURCE KEY (turn_id) REFERENCES turns (turn_id)
            DESTINATION KEY (section_id) REFERENCES sections (section_id)
            LABEL turn_section
            PROPERTIES ALL COLUMNS,
        temporal_edges
            KEY (edge_id)
            SOURCE KEY (source_doc_id) REFERENCES documents (doc_id)
            DESTINATION KEY (target_doc_id) REFERENCES documents (doc_id)
            LABEL changed_in
            PROPERTIES ALL COLUMNS,
        entity_aliases
            KEY (edge_id)
            SOURCE KEY (canonical_id) REFERENCES entities (entity_id)
            DESTINATION KEY (alias_id) REFERENCES entities (entity_id)
            LABEL alias_of
            PROPERTIES ALL COLUMNS
    );

COMMIT;
