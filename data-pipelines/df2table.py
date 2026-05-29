import logging
import re
import warnings
from datetime import time
from math import ceil

import pandas as pd

logger = logging.getLogger(__name__)

_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1
_SAMPLE_THRESHOLD = 0.9
_VALID_IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,29}$")


def _sanitize_column_name(name: str) -> str:
    """Uppercase name and replace characters invalid in Teradata identifiers with underscores."""
    sanitized = re.sub(r"[^A-Za-z0-9_]", "_", str(name))
    if not sanitized:
        raise ValueError(f"Column name {name!r} reduces to an empty string after sanitisation.")
    if sanitized[0].isdigit():
        sanitized = f"_{sanitized}"
    return sanitized.upper()


def _infer_teradata_type(series: pd.Series, sample_size: int) -> str:
    """
    Map a pandas Series to a Teradata SQL type string.

    For object-dtype columns, samples up to `sample_size` non-null values and
    tests for date, numeric, and string patterns before falling back to VARCHAR.
    """
    dtype_str = str(series.dtype)

    if dtype_str in ("bool", "boolean"):
        return "BYTEINT"

    if dtype_str in ("int8", "int16", "int32", "Int8", "Int16", "Int32"):
        return "INTEGER"

    if dtype_str in ("int64", "Int64"):
        non_null = series.dropna()
        if non_null.empty or (non_null.min() >= _INT32_MIN and non_null.max() <= _INT32_MAX):
            return "INTEGER"
        return "BIGINT"

    if "float" in dtype_str.lower():
        return "FLOAT"

    if "datetime" in dtype_str:
        non_null = series.dropna()
        if non_null.empty or (non_null.dt.time == time(0, 0)).all():
            return "DATE"
        return "TIMESTAMP(0)"

    if dtype_str == "category":
        # Sample before casting to avoid materialising the full series as object
        return _infer_teradata_type(series.head(sample_size).astype(object), sample_size)

    if dtype_str == "object":
        non_null = series.dropna()
        if non_null.empty:
            return "VARCHAR(100)"

        sample = non_null.head(sample_size)

        # Try date / datetime — suppress pandas format-inference warnings
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=UserWarning)
            parsed_dt = pd.to_datetime(sample, errors="coerce")
        if parsed_dt.notna().mean() >= _SAMPLE_THRESHOLD:
            if (parsed_dt.dropna().dt.time == time(0, 0)).all():
                return "DATE"
            return "TIMESTAMP(0)"

        # Try numeric
        parsed_num = pd.to_numeric(sample, errors="coerce")
        if parsed_num.notna().mean() >= _SAMPLE_THRESHOLD:
            non_null_num = parsed_num.dropna()
            if (non_null_num % 1 == 0).all():
                if non_null_num.min() >= _INT32_MIN and non_null_num.max() <= _INT32_MAX:
                    return "INTEGER"
                return "BIGINT"
            return "FLOAT"

        # VARCHAR — max observed length × 1.5, floor 10, ceiling 32000
        max_len = sample.astype(str).str.len().max()
        varchar_len = min(max(ceil(max_len * 1.5), 10), 32000)
        return f"VARCHAR({varchar_len})"

    return "VARCHAR(100)"


def df2table(
    df: pd.DataFrame,
    table_name: str,
    primary_index: str | list[str] | None = None,
    sample_size: int = 100,
    verbose: bool = False,
) -> str:
    """
    Generate a Teradata CREATE MULTISET VOLATILE TABLE DDL statement from a pandas DataFrame.

    Infers Teradata column types by sampling each column's values. Object-dtype columns
    are tested for date, numeric, and string patterns before defaulting to VARCHAR.
    Column names are uppercased and sanitised for Teradata compatibility.

    Args:
        df:            Source DataFrame.
        table_name:    Valid Teradata identifier for the volatile table (no database prefix).
        primary_index: Column name (str) or list of column names for the PRIMARY INDEX
                       clause. Pass None to omit the clause entirely.
        sample_size:   Number of non-null values sampled per column for type inference.
        verbose:       If True, logs the generated DDL at INFO level.

    Returns:
        A SQL string ready to execute against a Teradata session.

    Raises:
        ValueError: If `df` is empty or `table_name` is not a valid Teradata identifier.
        TypeError:  If `primary_index` is not a str, list, or None.

    Example:
        >>> import pandas as pd
        >>> df = pd.DataFrame({
        ...     "email":      ["user@example.com", "other@example.com"],
        ...     "account_id": [100001, 100002],
        ...     "open_date":  pd.to_datetime(["2023-01-15", "2024-06-01"]),
        ... })
        >>> print(df2table(df, "vt_accounts", primary_index="account_id"))
        CREATE MULTISET VOLATILE TABLE vt_accounts
        (
            EMAIL       VARCHAR(25),
            ACCOUNT_ID  INTEGER,
            OPEN_DATE   DATE
        ) PRIMARY INDEX (ACCOUNT_ID)
        ON COMMIT PRESERVE ROWS;
    """
    if df.empty:
        raise ValueError("DataFrame is empty — cannot infer column types.")

    if not _VALID_IDENTIFIER.match(table_name):
        raise ValueError(
            f"table_name {table_name!r} is not a valid Teradata identifier "
            "(must start with a letter, contain only letters/digits/underscores, max 30 chars)."
        )

    col_types = {
        _sanitize_column_name(col): _infer_teradata_type(df[col], sample_size)
        for col in df.columns
    }

    max_col_len = max(len(c) for c in col_types)
    col_lines = [
        f"    {col:<{max_col_len}}  {td_type}"
        for col, td_type in col_types.items()
    ]
    columns_block = ",\n".join(col_lines)

    if primary_index is None:
        pi_clause = ""
    elif isinstance(primary_index, str):
        pi_clause = f" PRIMARY INDEX ({_sanitize_column_name(primary_index)})"
    elif isinstance(primary_index, list):
        pi_cols = ", ".join(_sanitize_column_name(c) for c in primary_index)
        pi_clause = f" PRIMARY INDEX ({pi_cols})"
    else:
        raise TypeError(
            f"primary_index must be a str, list of str, or None — got {type(primary_index).__name__!r}."
        )

    ddl = (
        f"CREATE MULTISET VOLATILE TABLE {table_name}\n"
        "(\n"
        f"{columns_block}\n"
        f"){pi_clause}\n"
        "ON COMMIT PRESERVE ROWS;"
    )

    if verbose:
        logger.info("Generated DDL for volatile table '%s':\n%s", table_name, ddl)

    return ddl


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

    df2table(df, "vt_accounts", primary_index="account_id", verbose=True)
