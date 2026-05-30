# Teradata 16.x Quick Reference

A scannable cheat sheet for writing correct Teradata SQL fast — focused on the
dialect traps that bite people coming from Postgres/MySQL/ANSI SQL.

Environment this targets: **Teradata 16.x**, run via **Teradata Studio / SQL
Assistant** and **Python (teradatasql / SQLAlchemy)**, with **VOLATILE table**
create privileges. `REGEXP_*`, `QUALIFY`, JSON, and `PERIOD` types are available;
newer Vantage-only built-ins (e.g. `STRTOK_SPLIT_TO_TABLE`) are not assumed.

Replace `mydb.*` table names with your own.

---

## 1. Row limiting — there is NO `LIMIT`

```sql
SELECT TOP 100 *  FROM mydb.accounts;                    -- TOP after SELECT, no parens
SELECT * FROM mydb.accounts SAMPLE 100;                  -- random sample (non-deterministic)
SELECT TOP 100 acct_id, bal FROM mydb.accounts ORDER BY bal DESC;   -- real "top N"
```

- `LIMIT`/`OFFSET` → **not valid**. Use `TOP n` or `SAMPLE n`.
- `TOP` cannot coexist with `QUALIFY` in the same SELECT — for top-N-per-group use `QUALIFY`.

---

## 2. `QUALIFY` — filter on window functions, no subquery needed

```sql
-- Latest row per account (dedup to one)
SELECT acct_id, txn_date, amount
FROM mydb.transactions
QUALIFY ROW_NUMBER() OVER (PARTITION BY acct_id ORDER BY txn_date DESC) = 1;

-- Top 3 transactions per account
SELECT acct_id, txn_date, amount
FROM mydb.transactions
QUALIFY ROW_NUMBER() OVER (PARTITION BY acct_id ORDER BY amount DESC) <= 3;

-- De-dupe exact duplicate rows
SELECT *
FROM mydb.staging
QUALIFY ROW_NUMBER() OVER (PARTITION BY acct_id, txn_date, amount ORDER BY 1) = 1;

-- Keep rows above the per-group average
SELECT acct_id, amount
FROM mydb.transactions
QUALIFY amount > AVG(amount) OVER (PARTITION BY acct_id);
```

`ROW_NUMBER` = arbitrary tiebreak · `RANK` = gaps on ties · `DENSE_RANK` = no gaps.

---

## 3. Dates, times & the calendar

```sql
DATE '2026-05-30'                                  -- date literal
TIMESTAMP '2026-05-30 14:30:00'                    -- timestamp literal
CURRENT_DATE                                       -- today;  CURRENT_TIMESTAMP for now

txn_date BETWEEN DATE '2026-01-01' AND DATE '2026-03-31'   -- range (preserves partition elimination)
ADD_MONTHS(txn_date, -3)                           -- 3 months back
txn_date - INTERVAL '7' DAY                        -- explicit interval (self-documenting)
txn_date - DATE '2026-01-01'                       -- date - date = INTEGER days (not an interval!)

CAST(ts AS DATE)                                   -- timestamp -> date
CAST(txn_date AS DATE FORMAT 'YYYY-MM-DD')         -- format for display
TO_CHAR(txn_date, 'YYYY-MM-DD')                    -- also works
EXTRACT(YEAR FROM txn_date)                         -- year part (NOT in WHERE on a PPI column)

-- Built-in calendar for day-of-week / week / fiscal joins:
SELECT t.*, c.day_of_week, c.week_of_year, c.month_of_year
FROM mydb.transactions t
JOIN sys_calendar.calendar c ON c.calendar_date = t.txn_date;
```

**Rule:** never wrap the partition/date column in a function inside `WHERE` —
transform the literal side instead, or use a `BETWEEN` range. (See §6.)

---

## 4. Strings & matching

```sql
first_name || ' ' || last_name                      -- concat (|| , no CONCAT needed)
UPPER(x) · LOWER(x) · TRIM(x)                        -- case / whitespace
SUBSTR(x, 1, 3)                                      -- substring (1-indexed)
CHARACTERS(x)   -- or CHAR_LENGTH(x)                 -- length
POSITION('@' IN email)                              -- index of substring
OREPLACE(x, '-', '')                                -- replace all (Teradata-specific)
OTRANSLATE(x, 'abc', 'xyz')                         -- char-by-char translate
STRTOK(full_name, ' ', 1)                           -- nth space-delimited token

-- Case sensitivity (BIG trap): Teradata (BTET) mode default is NOT CASESPECIFIC,
-- so 'smith' = 'SMITH' is TRUE. ANSI mode = CASESPECIFIC. Force it explicitly:
WHERE last_name (CASESPECIFIC) = 'Smith'            -- force case-sensitive
WHERE UPPER(last_name) = 'SMITH'                    -- portable, recommended

-- Regex (16.x):
REGEXP_SUBSTR(x, '[0-9]{3}-[0-9]{4}')              -- first match
REGEXP_REPLACE(x, '[^0-9]', '')                    -- strip non-digits
WHERE REGEXP_SIMILAR(phone, '[0-9]{10}') = 1       -- full-match test (1/0)
```

---

## 5. Volatile-table pipeline (you have CREATE VOLATILE)

```sql
CREATE VOLATILE TABLE vt_stage AS (
    SELECT acct_id, SUM(amount) AS total
    FROM mydb.transactions
    WHERE txn_date BETWEEN DATE '2026-01-01' AND DATE '2026-03-31'
    GROUP BY acct_id
) WITH DATA
PRIMARY INDEX (acct_id)            -- choose PI to match downstream joins; avoid skew
ON COMMIT PRESERVE ROWS;           -- WITHOUT THIS the table empties on commit

COLLECT STATISTICS COLUMN (acct_id) ON vt_stage;   -- helps optimizer on the next join

SELECT a.acct_id, a.name, s.total
FROM mydb.accounts a
JOIN vt_stage s ON a.acct_id = s.acct_id;          -- co-located: both PI on acct_id

DROP TABLE vt_stage;               -- session-scoped; drop when done
```

- Empty shell instead of `AS (...) WITH DATA`: `CREATE VOLATILE TABLE vt (id INTEGER) ON COMMIT PRESERVE ROWS;`
- No database qualifier — volatile tables live in your session's spool.
- `MULTISET` (default) skips the duplicate-row check; use `SET` only when you truly need row-uniqueness enforcement.

---

## 6. SPOOL / product-join survival

`*** Failure 2646 No more spool space` almost always = a **product join**
(cartesian) or a redistribution on a skewed/mistyped key.

```sql
-- ALWAYS run EXPLAIN first on anything wide:
EXPLAIN
SELECT ...;
```

| EXPLAIN phrase | Meaning | Fix |
|---|---|---|
| `product join` | cartesian | add/repair the join predicate |
| `All-AMPs ... product join` | system-wide cross product | STOP — missing ON condition |
| `Redistribute` (repeated) | shuffling across AMPs | align join keys to PI / fix types |
| `No/Low Confidence` | stale or missing stats | `COLLECT STATISTICS` |
| `spool ... high estimated rows` | big intermediate | filter earlier, split into steps |

Two rules that prevent most blowups:
1. **Join keys must be the same data type.** `VARCHAR` joined to `INTEGER` forces a
   translation/redistribution and can explode spool. `CAST` to align.
2. **Filter on the partition column** with a bare range — never wrap it:
   ```sql
   WHERE txn_date BETWEEN DATE '2026-01-01' AND DATE '2026-03-31'   -- elimination kept
   WHERE EXTRACT(YEAR FROM txn_date) = 2026                          -- elimination KILLED
   WHERE CAST(txn_date AS DATE FORMAT 'YYYY-MM-DD') = '2026-01-01'   -- elimination KILLED
   ```

Other spool savers: `SELECT` only needed columns (cost scales rows × columns);
`UNION ALL` not `UNION` unless you need dedup; no `ORDER BY` inside CTEs/subqueries;
`NOT EXISTS` instead of `NOT IN` (NULL-safe + better plan).

---

## 7. `COLLECT STATISTICS` quick rules

```sql
COLLECT STATISTICS COLUMN (acct_id) ON mydb.transactions;          -- single col
COLLECT STATISTICS COLUMN (acct_id, txn_date) ON mydb.transactions; -- multi-col combo
COLLECT STATISTICS ON mydb.transactions;                            -- refresh all existing
HELP STATISTICS mydb.transactions;                                  -- what's collected + when
```

Collect on: PI columns, join columns, and `WHERE`/`GROUP BY` columns with high
cardinality. Stale stats → `Low Confidence` in EXPLAIN → bad plans.

---

## 8. Python — `teradatasql` and SQLAlchemy

**teradatasql (qmark `?` params — NOT `%s`):**
```python
import teradatasql, pandas as pd

with teradatasql.connect(host="HOST", user="USER", password="PW") as con:
    # Parameterized — safe + plan-cacheable. Never f-string user values into SQL.
    sql = """
        SELECT acct_id, txn_date, amount
        FROM mydb.transactions
        WHERE region = ? AND txn_date BETWEEN ? AND ?
    """
    df = pd.read_sql(sql, con, params=["FL", "2026-01-01", "2026-03-31"])

    # DDL / volatile table on the same connection/session:
    with con.cursor() as cur:
        cur.execute("CREATE VOLATILE TABLE vt (id INTEGER) ON COMMIT PRESERVE ROWS")
        cur.execute("INSERT INTO vt (?)", [101])
```

**SQLAlchemy (teradatasqlalchemy dialect):**
```python
from sqlalchemy import create_engine, text
import pandas as pd

engine = create_engine("teradatasql://USER:PW@HOST")     # add /?logmech=LDAP if needed
with engine.connect() as con:
    df = pd.read_sql(
        text("SELECT acct_id, amount FROM mydb.transactions WHERE region = :r"),
        con, params={"r": "FL"},
    )
```

**Pull discipline (financial-scale tables):**
- Never `SELECT *` into a DataFrame — name the columns you need.
- Push filters/aggregation server-side; don't pull raw rows to aggregate in pandas.
- One connection = one session: volatile tables vanish when the connection closes.
- Keep secrets in `.env` / a secret manager, never hardcoded.

---

## 9. Inspect / metadata

```sql
HELP TABLE mydb.accounts;          -- columns + types
SHOW TABLE mydb.accounts;          -- full DDL (PI, partitioning, SET/MULTISET)
HELP STATISTICS mydb.accounts;     -- collected stats + recency
HELP VOLATILE TABLE;               -- volatile tables in this session
SELECT * FROM DBC.DBCInfo;         -- Teradata version
SELECT DatabaseName, TableName FROM DBC.TablesV WHERE DatabaseName='mydb';   -- list tables
SELECT * FROM DBC.ColumnsV WHERE DatabaseName='mydb' AND TableName='accounts';
```

`SEL` is a valid abbreviation for `SELECT`.

---

## 10. Gotchas index (one-liners)

- No `LIMIT` → `TOP n` / `SAMPLE n`.
- `date - date` returns **INTEGER days**, not an interval.
- Default session may be **NOT CASESPECIFIC** → `'a' = 'A'` is true; force with `UPPER()` or `(CASESPECIFIC)`.
- Function on a partition column in `WHERE` kills partition elimination → full scan.
- Mismatched join-key types → redistribution / spool blowup.
- `NOT IN (subquery)` returns **zero rows** if the subquery yields any NULL → use `NOT EXISTS`.
- `UNION` sorts+dedups globally; default to `UNION ALL`.
- `ORDER BY` inside a CTE/subquery is wasted (sort discarded).
- Forgot `ON COMMIT PRESERVE ROWS` → volatile table empties on commit.
- Updating a PI column = delete+reinsert across AMPs; avoid bulk PI updates.
- Object/column names: 128-char limit.
- Run `EXPLAIN` before any wide query; grep for `product join`.
```
