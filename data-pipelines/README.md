# Data Pipelines

Python scripts for loading, cleaning, and transforming data — built from real-world development work in financial crimes technology and data engineering.

Each script is self-contained, well-documented, and ready to drop into your own project.

---

## Scripts

| Script | Description |
|---|---|
| [`excel_ingestor.py`](excel_ingestor.py) | Load any Excel sheet into a pandas DataFrame with automatic column sanitisation and numeric cleaning (currency, commas, accounting negatives, blanks) |

---

## Requirements

```bash
pip install pandas openpyxl
```

---

## Quick Example

```python
from excel_ingestor import ingest_excel

df = ingest_excel("data.xlsx")
```

See each script's module docstring for the full usage guide.

---

> Part of [In One We Trust](https://www.inonewetrust.com) — Faith · Code · Depth
