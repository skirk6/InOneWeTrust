import logging
import re
from datetime import time
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

_VALID_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,29}$")


def _sanitize_column_name(name: str) -> str:
    """Uppercase name and replace characters invalid in Teradata identifiers with underscores."""
    sanitized = re.sub(r"[^A-Za-z0-9_]", "_", str(name))
    if not sanitized:
        raise ValueError(f"Column name {name!r} reduces to an empty string after sanitisation.")
    if sanitized[0].isdigit():
        sanitized = f"_{sanitized}"
    if len(sanitized) > 30:
        raise ValueError(
            f"Column name {name!r} sanitises to {sanitized!r} ({len(sanitized)} chars), "
            "exceeding Teradata's 30-character identifier limit."
        )
    return sanitized.upper()


def _format_value(value: Any, dtype_str: str) -> str:
    """Format a single Python/pandas value as a Teradata SQL literal."""
    if pd.isna(value):  # must come first — pd.NA raises in bool/int context
        return "NULL"

    # bool must be checked before int — bool is a subclass of int in Python
    if dtype_str in ("bool", "boolean") or isinstance(value, bool):
        return "1" if value else "0"

    if "int" in dtype_str.lower():
        return str(int(value))

    if "float" in dtype_str.lower():
        # repr() preserves the decimal point (e.g. 9800.0, not 9800)
        return repr(float(value))

    if "datetime" in dtype_str:
        if hasattr(value, "time") and value.time() == time(0, 0):
            return f"DATE '{value.strftime('%Y-%m-%d')}'"
        # Truncates to seconds — consistent with df2table's TIMESTAMP(0) output
        return f"TIMESTAMP '{value.strftime('%Y-%m-%d %H:%M:%S')}'"

    # Default: string — escape embedded single quotes
    return f"'{str(value).replace(chr(39), chr(39) * 2)}'"


def df2insert(
    df: pd.DataFrame,
    table_name: str,
    batch: bool = True,
    verbose: bool = False,
) -> str:
    """
    Generate Teradata INSERT statements from a pandas DataFrame.

    Produces either a single batched INSERT ... SELECT ... UNION ALL statement
    (batch=True, the Teradata-idiomatic approach for programmatic loads) or
    individual INSERT INTO ... VALUES (...) statements per row (batch=False).

    Intended as a companion to df2table — generate the CREATE DDL with df2table,
    populate the table with df2insert.

    Args:
        df:         Source DataFrame. Column names are uppercased and sanitised.
        table_name: Name of the target volatile table (no database prefix).
        batch:      If True (default), emit a single INSERT ... SELECT ... UNION ALL
                    statement. If False, emit one INSERT ... VALUES (...) per row.
        verbose:    If True, logs the generated SQL at INFO level.

    Returns:
        A SQL string ready to execute against a Teradata session. Float values
        use repr() to preserve the decimal point (e.g. 9800.0, not 9800).
        Timestamps are truncated to second precision, consistent with df2table's
        TIMESTAMP(0) output.

    Raises:
        ValueError: If df is empty or table_name is not a valid Teradata identifier.

    Example:
        >>> import pandas as pd
        >>> df = pd.DataFrame({
        ...     "account_id": [100001, 100002],
        ...     "open_date":  pd.to_datetime(["2023-01-15", "2024-06-01"]),
        ...     "balance":    [1250.75, 9800.00],
        ... })
        >>> print(df2insert(df, "vt_accounts"))
        INSERT INTO vt_accounts
            (ACCOUNT_ID, OPEN_DATE, BALANCE)
        SELECT 100001, DATE '2023-01-15', 1250.75
        UNION ALL SELECT 100002, DATE '2024-06-01', 9800.0;
    """
    if df.empty:
        raise ValueError("DataFrame is empty — nothing to insert.")

    if not _VALID_IDENTIFIER.match(table_name):
        raise ValueError(
            f"table_name {table_name!r} is not a valid Teradata identifier "
            "(must start with a letter, contain only letters/digits/underscores, max 30 chars)."
        )

    columns = [_sanitize_column_name(col) for col in df.columns]
    col_list = ", ".join(columns)
    dtypes = [str(df[col].dtype) for col in df.columns]

    def format_row(row: Any) -> str:
        return ", ".join(_format_value(val, dtype) for val, dtype in zip(row, dtypes))

    if batch:
        rows = [format_row(row) for row in df.values]
        first, *rest = rows
        body = f"SELECT {first}"
        if rest:
            body += "\n" + "\n".join(f"UNION ALL SELECT {r}" for r in rest)
        sql = f"INSERT INTO {table_name}\n    ({col_list})\n{body};"
    else:
        header = f"INSERT INTO {table_name} ({col_list}) VALUES"
        sql = "\n".join(f"{header} ({format_row(row)});" for row in df.values)

    if verbose:
        logger.info(
            "Generated INSERT SQL for '%s' (%d row%s):\n%s",
            table_name, len(df), "s" if len(df) != 1 else "", sql,
        )

    return sql


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # fmt: off
    df = pd.DataFrame({
        "email_encrt_txt": ["A1B2C3D4E5F6", "B2C3D4E5F6A1"],
        "account_id":      [100001, 100002],
        "open_date":       pd.to_datetime(["2023-01-15", "2024-06-01"]),
        "balance":         [1250.75, 9800.00],
        "is_active":       [True, False],
    })
    # fmt: on

    logger.info("-- Batch (UNION ALL SELECT):")
    sql_batch = df2insert(df, "vt_accounts", batch=True, verbose=True)

    logger.info("\n-- Individual INSERTs:")
    sql_individual = df2insert(df, "vt_accounts", batch=False, verbose=True)
