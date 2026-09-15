-- ⚠️ 本文件由脚本生成，请勿手工修改
-- 生成命令：cd backend && uv run python scripts/db_init_sql.py
-- 单一源：app/models 的 ORM 元数据（与 RUN_MODE=local 的 create_all 同源，勿手写 DDL）
-- 幂等：所有 DDL 带 IF NOT EXISTS，可重复导入
-- 内容：仅表结构（PostgreSQL） + alembic 版本标记；业务数据由应用启动时/接口负责

-- 方言：postgresql

BEGIN;

CREATE TABLE IF NOT EXISTS audit_logs (
	id UUID NOT NULL, 
	request_id VARCHAR(64), 
	user_id UUID, 
	action VARCHAR(64) NOT NULL, 
	resource_type VARCHAR(64), 
	resource_id VARCHAR(64), 
	result VARCHAR(16) NOT NULL, 
	meta JSON NOT NULL, 
	tenant_id UUID, 
	workspace_id UUID, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_audit_logs_action ON audit_logs (action);

CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at ON audit_logs (created_at);

CREATE INDEX IF NOT EXISTS ix_audit_logs_request_id ON audit_logs (request_id);

CREATE INDEX IF NOT EXISTS ix_audit_logs_user_id ON audit_logs (user_id);


CREATE TABLE IF NOT EXISTS eval_runs (
	id UUID NOT NULL, 
	dataset_id UUID, 
	status VARCHAR(16) NOT NULL, 
	trigger VARCHAR(16) NOT NULL, 
	source_scope VARCHAR(16) NOT NULL, 
	config_fingerprint JSON NOT NULL, 
	metrics JSON NOT NULL, 
	total INTEGER NOT NULL, 
	passed INTEGER NOT NULL, 
	progress INTEGER NOT NULL, 
	error VARCHAR(1024), 
	started_at TIMESTAMP WITHOUT TIME ZONE, 
	finished_at TIMESTAMP WITHOUT TIME ZONE, 
	created_by UUID, 
	tenant_id UUID, 
	workspace_id UUID, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_eval_runs_created_at ON eval_runs (created_at);

CREATE INDEX IF NOT EXISTS ix_eval_runs_dataset_id ON eval_runs (dataset_id);

CREATE INDEX IF NOT EXISTS ix_eval_runs_status ON eval_runs (status);


CREATE TABLE IF NOT EXISTS jobs (
	id UUID NOT NULL, 
	kind VARCHAR(64) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	user_id UUID NOT NULL, 
	payload JSON NOT NULL, 
	result JSON NOT NULL, 
	progress INTEGER NOT NULL, 
	attempts INTEGER NOT NULL, 
	max_attempts INTEGER NOT NULL, 
	error VARCHAR(1024), 
	started_at TIMESTAMP WITHOUT TIME ZONE, 
	finished_at TIMESTAMP WITHOUT TIME ZONE, 
	tenant_id UUID, 
	workspace_id UUID, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_jobs_created_at ON jobs (created_at);

CREATE INDEX IF NOT EXISTS ix_jobs_kind ON jobs (kind);

CREATE INDEX IF NOT EXISTS ix_jobs_status ON jobs (status);

CREATE INDEX IF NOT EXISTS ix_jobs_user_id ON jobs (user_id);


CREATE TABLE IF NOT EXISTS users (
	id UUID NOT NULL, 
	username VARCHAR(64) NOT NULL, 
	password_hash VARCHAR(128) NOT NULL, 
	role VARCHAR(32) NOT NULL, 
	status VARCHAR(16) DEFAULT 'active' NOT NULL, 
	delete_reason VARCHAR(255), 
	token_version INTEGER DEFAULT '0' NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	deleted_at TIMESTAMP WITHOUT TIME ZONE, 
	deleted_by UUID, 
	PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_users_deleted_at ON users (deleted_at);

CREATE INDEX IF NOT EXISTS ix_users_username ON users (username);

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_username_active ON users (username) WHERE deleted_at IS NULL;


CREATE TABLE IF NOT EXISTS categories (
	id UUID NOT NULL, 
	user_id UUID NOT NULL, 
	name VARCHAR(64) NOT NULL, 
	color VARCHAR(16) NOT NULL, 
	sort_order INTEGER NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_categories_user_id ON categories (user_id);


CREATE TABLE IF NOT EXISTS chat_sessions (
	id UUID NOT NULL, 
	user_id UUID NOT NULL, 
	title VARCHAR(128) NOT NULL, 
	summary TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	deleted_at TIMESTAMP WITHOUT TIME ZONE, 
	deleted_by UUID, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_chat_sessions_deleted_at ON chat_sessions (deleted_at);

CREATE INDEX IF NOT EXISTS ix_chat_sessions_user_id ON chat_sessions (user_id);


CREATE TABLE IF NOT EXISTS documents (
	id UUID NOT NULL, 
	user_id UUID NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	source_type VARCHAR(32) NOT NULL, 
	content_hash VARCHAR(64), 
	storage_path VARCHAR(512), 
	status VARCHAR(16) NOT NULL, 
	extra JSON NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	deleted_at TIMESTAMP WITHOUT TIME ZONE, 
	deleted_by UUID, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_documents_content_hash ON documents (content_hash);

CREATE INDEX IF NOT EXISTS ix_documents_deleted_at ON documents (deleted_at);

CREATE INDEX IF NOT EXISTS ix_documents_user_id ON documents (user_id);


CREATE TABLE IF NOT EXISTS llm_settings (
	id UUID NOT NULL, 
	user_id UUID NOT NULL, 
	base_url VARCHAR(255) NOT NULL, 
	model VARCHAR(128) NOT NULL, 
	api_key_encrypted TEXT, 
	temperature FLOAT NOT NULL, 
	max_tokens INTEGER NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_llm_settings_user_id ON llm_settings (user_id);


CREATE TABLE IF NOT EXISTS usage_daily (
	id UUID NOT NULL, 
	user_id UUID NOT NULL, 
	day VARCHAR(10) NOT NULL, 
	requests INTEGER NOT NULL, 
	tokens_in INTEGER NOT NULL, 
	tokens_out INTEGER NOT NULL, 
	cost FLOAT NOT NULL, 
	errors INTEGER NOT NULL, 
	tenant_id UUID, 
	workspace_id UUID, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_usage_daily_user_day UNIQUE (user_id, day), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_usage_daily_day ON usage_daily (day);

CREATE INDEX IF NOT EXISTS ix_usage_daily_user_id ON usage_daily (user_id);


CREATE TABLE IF NOT EXISTS wiki_spaces (
	id UUID NOT NULL, 
	owner_id UUID, 
	name VARCHAR(128) NOT NULL, 
	source_type VARCHAR(16) NOT NULL, 
	root_path VARCHAR(512) NOT NULL, 
	last_synced_at TIMESTAMP WITHOUT TIME ZONE, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	deleted_at TIMESTAMP WITHOUT TIME ZONE, 
	deleted_by UUID, 
	PRIMARY KEY (id), 
	FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_wiki_spaces_deleted_at ON wiki_spaces (deleted_at);

CREATE INDEX IF NOT EXISTS ix_wiki_spaces_owner_id ON wiki_spaces (owner_id);


CREATE TABLE IF NOT EXISTS chunks (
	id UUID NOT NULL, 
	document_id UUID NOT NULL, 
	chunk_index INTEGER NOT NULL, 
	content TEXT NOT NULL, 
	meta JSON NOT NULL, 
	vector_id VARCHAR(64), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	deleted_at TIMESTAMP WITHOUT TIME ZONE, 
	deleted_by UUID, 
	PRIMARY KEY (id), 
	FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_chunks_deleted_at ON chunks (deleted_at);

CREATE INDEX IF NOT EXISTS ix_chunks_document_id ON chunks (document_id);


CREATE TABLE IF NOT EXISTS memory_facts (
	id UUID NOT NULL, 
	user_id UUID NOT NULL, 
	fact TEXT NOT NULL, 
	category VARCHAR(32) NOT NULL, 
	confidence FLOAT NOT NULL, 
	source_session_id UUID, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	deleted_at TIMESTAMP WITHOUT TIME ZONE, 
	deleted_by UUID, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(source_session_id) REFERENCES chat_sessions (id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_memory_facts_deleted_at ON memory_facts (deleted_at);

CREATE INDEX IF NOT EXISTS ix_memory_facts_user_id ON memory_facts (user_id);


CREATE TABLE IF NOT EXISTS messages (
	id UUID NOT NULL, 
	session_id UUID NOT NULL, 
	role VARCHAR(16) NOT NULL, 
	content TEXT NOT NULL, 
	extra JSON NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	deleted_at TIMESTAMP WITHOUT TIME ZONE, 
	deleted_by UUID, 
	PRIMARY KEY (id), 
	FOREIGN KEY(session_id) REFERENCES chat_sessions (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_messages_deleted_at ON messages (deleted_at);

CREATE INDEX IF NOT EXISTS ix_messages_session_id ON messages (session_id);


CREATE TABLE IF NOT EXISTS session_files (
	id UUID NOT NULL, 
	session_id UUID NOT NULL, 
	filename VARCHAR(255) NOT NULL, 
	content TEXT NOT NULL, 
	bytes_size INTEGER DEFAULT '0' NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	deleted_at TIMESTAMP WITHOUT TIME ZONE, 
	deleted_by UUID, 
	PRIMARY KEY (id), 
	FOREIGN KEY(session_id) REFERENCES chat_sessions (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_session_files_deleted_at ON session_files (deleted_at);

CREATE INDEX IF NOT EXISTS ix_session_files_session_id ON session_files (session_id);


CREATE TABLE IF NOT EXISTS todos (
	id UUID NOT NULL, 
	user_id UUID NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	priority INTEGER NOT NULL, 
	due_date DATE, 
	category_id UUID, 
	tags JSON DEFAULT '[]' NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	deleted_at TIMESTAMP WITHOUT TIME ZONE, 
	deleted_by UUID, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(category_id) REFERENCES categories (id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_todos_category_id ON todos (category_id);

CREATE INDEX IF NOT EXISTS ix_todos_deleted_at ON todos (deleted_at);

CREATE INDEX IF NOT EXISTS ix_todos_user_id ON todos (user_id);


CREATE TABLE IF NOT EXISTS wiki_pages (
	id UUID NOT NULL, 
	user_id UUID NOT NULL, 
	space_id UUID NOT NULL, 
	rel_path VARCHAR(512) NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	slug VARCHAR(255) NOT NULL, 
	document_id UUID, 
	content_hash VARCHAR(64), 
	mtime FLOAT NOT NULL, 
	size INTEGER NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	deleted_at TIMESTAMP WITHOUT TIME ZONE, 
	deleted_by UUID, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_wiki_page_space_path UNIQUE (space_id, rel_path), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(space_id) REFERENCES wiki_spaces (id) ON DELETE CASCADE, 
	FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_wiki_pages_deleted_at ON wiki_pages (deleted_at);

CREATE INDEX IF NOT EXISTS ix_wiki_pages_document_id ON wiki_pages (document_id);

CREATE INDEX IF NOT EXISTS ix_wiki_pages_slug ON wiki_pages (slug);

CREATE INDEX IF NOT EXISTS ix_wiki_pages_space_id ON wiki_pages (space_id);

CREATE INDEX IF NOT EXISTS ix_wiki_pages_user_id ON wiki_pages (user_id);


CREATE TABLE IF NOT EXISTS wiki_links (
	id UUID NOT NULL, 
	user_id UUID NOT NULL, 
	space_id UUID NOT NULL, 
	source_page_id UUID NOT NULL, 
	target_slug VARCHAR(255) NOT NULL, 
	target_page_id UUID, 
	alias VARCHAR(255), 
	kind VARCHAR(16) NOT NULL, 
	relation VARCHAR(32), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(space_id) REFERENCES wiki_spaces (id) ON DELETE CASCADE, 
	FOREIGN KEY(source_page_id) REFERENCES wiki_pages (id) ON DELETE CASCADE, 
	FOREIGN KEY(target_page_id) REFERENCES wiki_pages (id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_wiki_links_source_page_id ON wiki_links (source_page_id);

CREATE INDEX IF NOT EXISTS ix_wiki_links_space_id ON wiki_links (space_id);

CREATE INDEX IF NOT EXISTS ix_wiki_links_target_page_id ON wiki_links (target_page_id);

CREATE INDEX IF NOT EXISTS ix_wiki_links_target_slug ON wiki_links (target_slug);

CREATE INDEX IF NOT EXISTS ix_wiki_links_user_id ON wiki_links (user_id);


-- ---- alembic 版本标记（导入后 alembic upgrade 不会重复建表）----
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
DELETE FROM alembic_version;
INSERT INTO alembic_version (version_num) VALUES ('e7f8a9b0c1d2');

COMMIT;
