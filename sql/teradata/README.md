# Teradata SQL

Investigation queries and patterns for Teradata MPP environments, built from real financial crimes technology work.

---

## Queries

| File | Description |
|---|---|
| [`fuzzy_name_match.sql`](fuzzy_name_match.sql) | Match an upstream full name against a split first/middle/last name table using normalization, token extraction, and SOUNDEX phonetic scoring. Returns matches at or above a configurable score threshold. |

---

## Notes

- All queries use CTEs for readability — no nested subqueries
- Table and column names are placeholders; swap them for your environment
- Tested against Teradata syntax; SOUNDEX is a native built-in, no additional licensing required
