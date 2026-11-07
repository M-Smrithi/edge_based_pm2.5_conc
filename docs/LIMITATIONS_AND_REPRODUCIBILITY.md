# Limitations, deviations and reproducibility

## Scientific limitations
* **Software simulation.** The edge gateway is Python code on a general-purpose computer. No Raspberry Pi, microcontroller, radio link, power or memory constraint is modelled. Latency numbers are host-specific.
* **Artificial missingness** (uniform cells or contiguous single-sensor blocks of 6–48 hours) is a controlled stand-in for real outages, which may be correlated across sensors, weather and pollution events.
* **One imputation strategy** (training-set median) and one model family were studied; a small validation-only candidate comparison is included, not a model search.
* **Same-hour estimation**, not forecasting; the model sees only co-located sensors of the same hour.
* **Network coverage.** Files lacking a sensor column, or with blank/contradictory units, are held for review or excluded; they are never silently "fixed". The analysed stations are therefore a subset of the archive and may not represent India as a whole.
* **Unseen-station test** uses a modest number of hash-selected stations; its variance is not estimated across alternative selections.
* **Hourly PM2.5 categories** use CPCB 24-hour breakpoints purely as a descriptive grouping.
* Outputs are not health advice.

## Differences from the original proposal
* Data source: CPCB station-wise data (Kaggle) instead of the UCI Air Quality dataset named in the original report; approved by the project owner.
* The original report said incomplete records would be removed; this study keeps them (median-imputed), because incomplete inputs are the research subject.
* A small validation-only model comparison was added (random forest is the preferred family).

## Build-environment deviations (honest list)
* No internet package access in the build sandbox: the UI uses **no React, CDN, web fonts or chart library** — plain JavaScript, a small in-house SVG chart module and the system font stack; the backend uses stdlib `sqlite3` with SQL migrations instead of an ORM; `unittest` instead of pytest.
* The optional MQTT mode was not implemented.
* Browser checks were done with headless Chromium (Playwright) in the sandbox; see `docs/TESTING.md`.

## Reproducibility
* Seeds: data split hash seed 42; model seeds in the model manifest; experiment seed 2024 (+ rate and trial offsets).
* Each model/experiment manifest stores dataset checksum, benchmark checksum, library versions, platform and CPU count.
* `python manage.py verify` re-checks dataset and model checksums; the Experiment Manager's *Reproduce* action re-runs an experiment and reports whether every trial result is bit-identical (expected on the same machine and library versions).
* Joblib model files are pickles: they are only ever loaded after their SHA-256 matches the manifest. Do not place untrusted files in `storage/models/`.
* Large data: records are held as float32 NumPy arrays (about 0.4 GB for 3.3 M rows); nothing is silently sampled. Random-forest training uses a documented bootstrap fraction per tree (`max_samples`) — every training row remains eligible for every tree. Latency uses a fixed, documented set of 200 records. Experiments score all frozen test records.
