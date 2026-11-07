CREATE TABLE users(
  id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE COLLATE NOCASE, name TEXT NOT NULL DEFAULT '',
  password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','analyst')), active INTEGER NOT NULL DEFAULT 1,
  failed_logins INTEGER NOT NULL DEFAULT 0, locked_until TEXT, created_utc TEXT NOT NULL, last_login_utc TEXT);
CREATE TABLE audit_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, user_id INTEGER, user_email TEXT, action TEXT NOT NULL,
  target TEXT, detail TEXT, ip TEXT);
CREATE INDEX idx_audit_ts ON audit_log(ts);
CREATE TABLE batches(
  id INTEGER PRIMARY KEY AUTOINCREMENT, created_utc TEXT NOT NULL, user_id INTEGER, n_files INTEGER NOT NULL DEFAULT 0, note TEXT);
CREATE TABLE files(
  id INTEGER PRIMARY KEY AUTOINCREMENT, file_name TEXT NOT NULL, sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL,
  station TEXT, status TEXT NOT NULL CHECK(status IN ('accepted','accepted_recovered','pending_review','rejected')),
  audit_json TEXT NOT NULL, reasons TEXT, decisions_json TEXT, batch_id INTEGER, uploaded_by INTEGER, uploaded_utc TEXT NOT NULL,
  overlap_json TEXT, UNIQUE(sha256, file_name));
CREATE INDEX idx_files_sha ON files(sha256);
CREATE INDEX idx_files_status ON files(status);
CREATE TABLE dataset_versions(
  id TEXT PRIMARY KEY, created_utc TEXT NOT NULL, created_by INTEGER, rows INTEGER, n_files INTEGER, n_stations INTEGER,
  records_sha256 TEXT, note TEXT, job_id INTEGER);
CREATE TABLE benchmarks(
  id TEXT PRIMARY KEY, created_utc TEXT NOT NULL, dataset_version TEXT, sha256 TEXT, active INTEGER NOT NULL DEFAULT 0, created_by INTEGER);
CREATE TABLE jobs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('queued','running','succeeded','failed','cancelled')),
  params TEXT NOT NULL DEFAULT '{}', progress REAL NOT NULL DEFAULT 0, message TEXT, result TEXT, error TEXT,
  created_utc TEXT NOT NULL, started_utc TEXT, finished_utc TEXT, pid INTEGER, user_id INTEGER, log_path TEXT);
CREATE TABLE models(
  id TEXT PRIMARY KEY, created_utc TEXT NOT NULL, dataset_version TEXT, benchmark_id TEXT, selected TEXT, model_sha256 TEXT,
  status TEXT NOT NULL CHECK(status IN ('candidate','active','rejected','archived')) DEFAULT 'candidate',
  metrics_json TEXT, job_id INTEGER, note TEXT, status_changed_utc TEXT);
CREATE TABLE model_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, model_id TEXT NOT NULL, action TEXT NOT NULL, user_email TEXT, detail TEXT);
CREATE TABLE experiments(
  id TEXT PRIMARY KEY, created_utc TEXT NOT NULL, model_id TEXT, benchmark_id TEXT, dataset_version TEXT, trials INTEGER,
  seed INTEGER, job_id INTEGER, reproduces TEXT, reproduction_json TEXT);
CREATE TABLE prediction_runs(
  token TEXT PRIMARY KEY, created_utc TEXT NOT NULL, expires_utc TEXT NOT NULL, rows INTEGER, model_id TEXT, path TEXT);
CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
