# API reference

JSON over HTTP. All unsafe methods (POST/PUT/DELETE) under `/api` need the header `X-CSRF-Token` (get it from `GET /api/csrf`;
it is bound to the session cookie). Admin routes need a session cookie from `POST /api/auth/login`; mutating admin routes need the
`admin` role (`analyst` is read-only). Errors: `{"error": "..."}` with 400/401/403/404/409/413/503.

## Public (no login)
| Method & path | Purpose |
|---|---|
| `GET /api/csrf` | CSRF token for this session |
| `GET /api/public/status` | which parts exist (model, data, experiment) + headline facts of the active model/dataset |
| `GET /api/public/dashboard[?station=CODE]` | air-quality aggregates (overall or one station) |
| `GET /api/public/research` | latest experiment of the active model: summary rows, latency, candidates, benchmark, dataset, figures |
| `GET /api/public/figure/<exp>/<name>.png` | rendered report figure (whitelisted names) |
| `GET /api/public/methodology` | schema, ranges, constants used by the study |
| `POST /api/public/predict` | `{"features": {"PM10": 120, ...}}` → estimate, category, imputed/invalid sensors, latency. `503` if no active model |
| `POST /api/public/predict-csv` | multipart `file` (≤5 MB, ≤20,000 rows). Recognised headers: `PM10`… or CPCB style `PM10 (ug/m3)`; verified unit conversions only. Returns summary, preview, download token. Uploaded data is never added to training |
| `GET /api/public/predict-download/<token>` | result CSV (expires after 24 h) |
| `GET /api/public/template.csv` | input template |

## Auth
`POST /api/auth/login {email,password}` · `POST /api/auth/logout` · `GET /api/auth/me` · `POST /api/auth/password {current,new}`.
Five failed logins lock the account for 15 minutes. There is no public registration.

## Admin (`/api/admin/...`)
| Path | Notes |
|---|---|
| `GET overview` | counts, active model, running jobs, stale-dataset flag |
| `POST files/upload` (multipart `files`, optional `batch_id`) | validates each file; stores the original; returns per-file verdict, reasons, overlap explanation |
| `GET files?status=&q=&sort=&page=&size=` · `GET files/<id>` | registry and full audit of one file |
| `POST files/<id>/decision` | `{action: approve_blank_unit, feature}` · `approve_structural_absence` · `reject` · `reopen` (audit-logged) |
| `GET batches` · `GET datasets` · `GET datasets/<ds-NNNN>` | upload history, versions/benchmarks, manifest |
| `POST jobs {kind, params}` | kinds: `build_dataset`, `train`, `experiment`, `retrain`, `reproduce_experiment`; returns `202 {job_id}`. One heavy job runs at a time, others queue |
| `GET jobs` · `GET jobs/<id>` (with log tail) · `POST jobs/<id>/cancel` | |
| `GET models` · `GET models/<id>` · `GET models/<id>/checks` | registry, details, promotion checks |
| `POST models/<id>/promote {confirm: "<id>"}` | `409` + failed checks if any check fails |
| `POST models/<id>/reject` · `.../archive` `{note}` | active model cannot be rejected/archived |
| `POST models-rollback {to, confirm}` | restore an archived model after an integrity check |
| `GET experiments` · `GET experiments/<id>` · `GET experiments/<id>/results.csv` | |
| `GET audit?q=&action=&page=&format=csv` | audit log |
| `GET/PUT settings` · `POST users` · `POST users/<id>/active` | |

### Promotion checks
status candidate/archived · artifact integrity (SHA-256, reload, schema, medians, finite predictions) · beats the median baseline on every test set ·
latency recorded · **no regression against the active model on the same frozen benchmark** (the active model is re-scored if the benchmark differs) ·
typed confirmation of the model id.
