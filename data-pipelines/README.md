# Data Pipelines

Python tools for loading, cleaning, transforming, and exploring data — built from real-world work in financial crimes technology and data engineering.

Each script is self-contained and documented in its module docstring.

---

## Scripts

| Script | Description |
|---|---|
| [`excel_ingestor.py`](excel_ingestor.py) | Load any Excel sheet into a pandas DataFrame with automatic column sanitisation and numeric cleaning (currency, commas, accounting negatives, percentages, blanks). |
| [`sttm_function.py`](sttm_function.py) | Scan a Python source file for embedded SQL and return a deduplicated, sorted DataFrame of [Database, Table, Column] lineage — the source-to-target mapping (STTM) artefact every AML data engineer ends up building by hand. |
| [`pbkdf2.py`](pbkdf2.py) | Generate a deterministic PBKDF2-HMAC-SHA256 hash from an email address. Matches the hashing scheme used by Teradata databases storing pseudonymous PII — given a list of plain emails, builds a DataFrame of hashed identifiers ready to query against encrypted-email columns. |
| [`df2table.py`](df2table.py) | Generate a Teradata `CREATE MULTISET VOLATILE TABLE` DDL statement from a pandas DataFrame. Infers Teradata column types (INTEGER, BIGINT, FLOAT, DATE, TIMESTAMP, BYTEINT, VARCHAR) by sampling each column, with optional PRIMARY INDEX support. |
| [`GetUpstreamApp.py`](GetUpstreamApp.py) | Interactive desktop app for exploring an Excel dataset by date range and column values. Uses tkinter with an automatic PyQt5 fallback so it runs on Windows, macOS, and Linux without setup. |

---

## Requirements

Per-script, in each module docstring. The core dependency across all of them is:

```bash
pip install pandas openpyxl
```

`GetUpstreamApp.py` additionally needs `tkcalendar` (auto-installs on first run) or `PyQt5` as a fallback.

---

## Quick Example

```python
from excel_ingestor import ingest_excel

df = ingest_excel("data.xlsx")
```

See each script's module docstring for the full usage guide.

---

> Part of [In One We Trust](https://www.inonewetrust.com) — Faith · Code · Depth. The `excel_ingestor`, `sttm_function`, `pbkdf2`, and `df2table` scripts are featured on [/code](https://www.inonewetrust.com/code).
