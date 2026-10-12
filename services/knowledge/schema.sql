CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS knowledge;
CREATE TABLE IF NOT EXISTS knowledge.documents (
 id text PRIMARY KEY, scope text NOT NULL, product text NOT NULL, version text NOT NULL,
 title text NOT NULL, source text NOT NULL, sha256 text NOT NULL, suffix text NOT NULL,
 parent_id text REFERENCES knowledge.documents(id), reconstruction boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(scope,product,version,sha256), UNIQUE(id,scope)
);
CREATE TABLE IF NOT EXISTS knowledge.chunks (
 id bigserial PRIMARY KEY, document_id text NOT NULL,
 scope text NOT NULL, locator text NOT NULL, kind text NOT NULL, body text NOT NULL,
 title_vector vector(384) NOT NULL, body_vector vector(384) NOT NULL,
 tokens bytea NOT NULL, token_count int NOT NULL CHECK(token_count BETWEEN 1 AND 256),
 terms tsvector GENERATED ALWAYS AS (to_tsvector('simple',body)) STORED,
 FOREIGN KEY(document_id,scope) REFERENCES knowledge.documents(id,scope)
);
CREATE INDEX IF NOT EXISTS knowledge_terms ON knowledge.chunks USING gin(terms);
CREATE INDEX IF NOT EXISTS knowledge_scope ON knowledge.chunks(scope,document_id);
CREATE INDEX IF NOT EXISTS knowledge_body_vector ON knowledge.chunks USING hnsw(body_vector vector_cosine_ops);
CREATE INDEX IF NOT EXISTS knowledge_title_vector ON knowledge.chunks USING hnsw(title_vector vector_cosine_ops);
CREATE INDEX IF NOT EXISTS knowledge_documents_scope ON knowledge.documents(scope,product,version);
ALTER TABLE knowledge.documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge.documents FORCE ROW LEVEL SECURITY;
ALTER TABLE knowledge.chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge.chunks FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS knowledge_documents_scope ON knowledge.documents;
CREATE POLICY knowledge_documents_scope ON knowledge.documents
 USING (scope=ANY(string_to_array(current_setting('arcia.read_scopes',true),'|'))) WITH CHECK(scope=current_setting('arcia.scope',true));
DROP POLICY IF EXISTS knowledge_chunks_scope ON knowledge.chunks;
CREATE POLICY knowledge_chunks_scope ON knowledge.chunks
 USING (scope=ANY(string_to_array(current_setting('arcia.read_scopes',true),'|'))) WITH CHECK(scope=current_setting('arcia.scope',true));
GRANT USAGE ON SCHEMA knowledge TO arcia_knowledge;
GRANT SELECT,INSERT ON ALL TABLES IN SCHEMA knowledge TO arcia_knowledge;
GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA knowledge TO arcia_knowledge;
