# Testing — what ran and what did not

Command: `python manage.py test`  (stdlib `unittest`; pytest could not be installed offline but is compatible).
Result in the build environment: **50 tests, all passed** (≈30 s, Python 3.13, scikit-learn 1.9.1).

| Area | Tests | What is covered |
|---|---|---|
| Data pipeline (`tests/test_data_pipeline.py`, 18) | passed | header resolution (exact / alias / verified SI conversion / refusal to guess units), no target leakage, cleaning policy (duplicates, out-of-range, bad targets, partial rows kept, all-missing rows dropped), station-name normalisation, per-file audit verdicts, bad/empty/non-UTF-8 files rejected without crashing, audit works without `stations_info.csv` and never modifies inputs, content-addressed read-only originals, de-duplication counts (identical vs conflicting), atomic dataset build and cleanup after failure, frozen benchmark: held-out stations disjoint from training, training precedes test, test records unchanged after dataset growth |
| ML (`tests/test_ml.py`, 14) | passed | simulator: exact rate of observed cells, seeded determinism, consecutive blocks contiguous / single sensor / single station / never across a gap, input never mutated; training: medians fitted on the training split only, selection rule, artifacts complete and checksum-verified, model beats median baseline, corrupted artifact detected and never loaded, failed training leaves no model directory; gateway: imputation, invalid/unknown fields, all-missing record; experiments: same frozen records, error non-decreasing with missingness, achieved rate, latency scenarios, bit-identical reproduction, refusal on benchmark mismatch |
| Backend security & workflows (`tests/test_backend.py`, 18) | passed | every admin route rejects anonymous access, admin pages redirect, no registration route, CSRF enforced, scrypt-hashed passwords + generic login errors, lockout, analyst read-only (backend-enforced), weak-password and last-admin protection, deactivated session stops, headers/cookie, no hard-coded credentials; upload flow (accept, byte-identical duplicate, overlap explanation, bad extension/empty/oversize, path-traversal filename, review decisions), full lifecycle through the real job worker (subprocess dispatch, candidate ≠ active, typed-confirmation promotion, cumulative second batch → new dataset version with old versions and benchmark untouched, **failed training does not replace the active model**, regressing/rejected candidates blocked, rollback), public CSV prediction (validation, expiry, not added to training); CSP-clean templates, no `innerHTML`, JavaScript syntax (`node --check`) |

## Browser checks (manual scripts with headless Chromium via Playwright — not part of the unittest suite)
Run against the final application: all public and admin pages load at 1280 px and 390 px widths with **no console or page errors**;
Prediction Studio single-record form (including an invalid RH value being substituted) and CSV upload; admin login, file upload
with progress, file-detail dialog, model registry. Screenshots were inspected by eye.

## Could not run / not done
* **Physical edge hardware, MQTT:** not used; the optional MQTT mode is not implemented.
* **Firefox / Safari, screen readers, automated accessibility audit:** not run (semantic markup, focus styles, labelled controls, keyboard-operable dialogs are implemented but not audited with a tool).
* **Load / concurrency testing, HTTPS deployment, gunicorn:** not run (the Flask development server was used).
* **pytest and React/Vite tooling:** unavailable (no package index access); equivalent unittest tests and a no-build frontend were used.
