"""
excel_ingestor.py
-----------------
Loads an Excel sheet into a pandas DataFrame with automatic column-name
sanitisation and optional numeric cleaning — strips currency symbols,
thousand-separator commas, accounting-style negatives, percentage signs,
and Excel blanks in one pass.

Requirements
------------
    pip install pandas openpyxl

Logging
-------
This module uses Python's standard logging system under the logger name
``excel_ingestor``. The load summary (verbose=True) is emitted at INFO
level; warnings are emitted at WARNING level.

By default (no logging configured by the caller) these messages are
silently absorbed — standard library behaviour for a module logger.
Configure logging in your application to see them:

    import logging
    logging.basicConfig(level=logging.INFO)   # see full summary + warnings
    logging.getLogger("excel_ingestor").setLevel(logging.WARNING)  # warnings only

The CLI entry point configures its own minimal handler automatically.

Quick Start
-----------
Simplest use — first sheet, all defaults on:

    from excel_ingestor import ingest_excel

    df = ingest_excel("data.xlsx")

Load a named sheet, suppress the summary log:

    df = ingest_excel("report.xlsx", sheet_name="Summary", verbose=False)

Clean only specific numeric columns (skip auto-detection):

    df = ingest_excel(
        "transactions.xlsx",
        sheet_name="Q1",
        numeric_cols=["amount", "balance", "fee"],
    )

Header is on row 3 (0-indexed = 2) with a subtitle row right below it:

    df = ingest_excel("export.xlsx", header_row=2, skip_rows=[3])

Force certain columns to a specific dtype before any cleaning runs:

    df = ingest_excel(
        "accounts.xlsx",
        dtype_map={"account_id": str, "zip_code": str},
    )

List all sheets in a workbook before deciding which to load:

    import pandas as pd
    print(pd.ExcelFile("data.xlsx").sheet_names)

Run from the command line (prints first 10 rows):

    python excel_ingestor.py data.xlsx
    python excel_ingestor.py data.xlsx "Sheet2"
    python excel_ingestor.py --help

Author : In One We Trust (https://www.inonewetrust.com)
GitHub : https://github.com/skirk6/InOneWeTrust
"""

import logging
import re
import sys
from pathlib import Path
from typing import Any, NoReturn

import numpy as np
import pandas as pd

# Module-level logger — callers configure handlers and level; this module
# never touches the root logger or calls basicConfig itself.
logger = logging.getLogger(__name__)

# Public API surface — internal helpers are excluded from wildcard imports.
__all__ = ["ingest_excel"]


# ──────────────────────────────────────────────
# Core Ingestion Function
# ──────────────────────────────────────────────

def ingest_excel(
    file_path: str,
    sheet_name: str | int = 0,
    header_row: int = 0,
    numeric_cols: list[str] | None = None,
    strip_currency: bool = True,
    strip_commas: bool = True,
    coerce_numeric: bool = True,
    dtype_map: dict[str, Any] | None = None,
    skip_rows: int | list[int] | None = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Load an Excel sheet into a cleaned pandas DataFrame.

    Parameters
    ----------
    file_path : str
        Absolute or relative path to the Excel file (.xlsx / .xls / .xlsm / .xlsb).
    sheet_name : str or int, optional
        Sheet name or zero-based index to load. Default: first sheet (0).
    header_row : int, optional
        Row index (0-based) to use as column headers. Default: 0.
    numeric_cols : list of str, optional
        Specific columns to clean as numbers. None = auto-detect all likely
        numeric columns using the full cleaning pipeline as a probe.
    strip_currency : bool, optional
        Remove $, £, €, ¥ before numeric conversion. Default: True.
    strip_commas : bool, optional
        Remove thousand-separator commas (e.g. 1,234 → 1234). Default: True.
    coerce_numeric : bool, optional
        Apply pd.to_numeric after cleaning; unparseable values become NaN. Default: True.
    dtype_map : dict of {str: Any}, optional
        Column-to-dtype map forwarded directly to pd.read_excel (e.g. ``{"id": str}``).
    skip_rows : int or list of int, optional
        Row(s) to skip after the header row (forwarded to pd.read_excel skiprows).
    verbose : bool, optional
        Emit a load-summary report via logger.info(). Default: True.

    Returns
    -------
    pd.DataFrame
        Cleaned DataFrame ready for analysis or export.

    Raises
    ------
    FileNotFoundError
        file_path does not exist on disk.
    ValueError
        File extension is not a recognised Excel format.
    KeyError
        sheet_name is not found in the workbook.
    RuntimeError
        Unexpected error from pandas or openpyxl.

    Examples
    --------
    # 1 — Simplest use: load the first sheet with all defaults
    df = ingest_excel("sales_data.xlsx")

    # 2 — Named sheet, only clean specific columns, suppress the summary
    df = ingest_excel(
        "q1_report.xlsx",
        sheet_name="March",
        numeric_cols=["revenue", "expenses", "net"],
        verbose=False,
    )

    # 3 — Header on row 3, skip the subtitle row beneath it, force ID to string
    df = ingest_excel(
        "bank_export.xlsx",
        header_row=2,
        skip_rows=[3],
        dtype_map={"account_id": str},
    )

    # 4 — Turn off all automatic cleaning and handle types yourself
    df = ingest_excel(
        "raw_data.xlsx",
        coerce_numeric=False,
        verbose=False,
    )
    """

    path = Path(file_path)

    # ── 1. Validate file path ──────────────────
    if not path.exists():
        raise FileNotFoundError(
            f"[ingest_excel] File not found: '{file_path}'\n"
            "Check the path and try again."
        )

    if path.suffix.lower() not in (".xlsx", ".xls", ".xlsm", ".xlsb"):
        raise ValueError(
            f"[ingest_excel] Unsupported file type: '{path.suffix}'. "
            "Expected .xlsx, .xls, .xlsm, or .xlsb."
        )

    # ── 2. Load workbook ───────────────────────
    try:
        df = pd.read_excel(
            file_path,
            sheet_name=sheet_name,
            header=header_row,
            skiprows=skip_rows,
            dtype=dtype_map,
        )
    except Exception as exc:
        _handle_read_error(exc, path, sheet_name)

    if df.empty:
        logger.warning("Sheet '%s' loaded but contains no data.", sheet_name)
        return df

    # ── 3. Sanitise column names ───────────────
    df.columns = _clean_column_names(df.columns)

    # ── 4. Number cleaning ─────────────────────
    if coerce_numeric:
        target_cols = _resolve_target_cols(df, numeric_cols, strip_currency, strip_commas)
        for col in target_cols:
            df[col] = _clean_numeric_series(
                df[col], strip_currency=strip_currency, strip_commas=strip_commas
            )

    # ── 5. Verbose summary ─────────────────────
    if verbose:
        _log_summary(df, path, sheet_name)

    return df


# ──────────────────────────────────────────────
# Helper: Column Name Sanitiser
# ──────────────────────────────────────────────

def _clean_column_names(columns: pd.Index) -> list[str]:
    """Lowercase, strip whitespace, replace special characters with underscores, and deduplicate collisions.

    First occurrence keeps its name; collisions are suffixed _1, _2, …
    """
    seen: dict[str, int] = {}
    result: list[str] = []
    for col in columns:
        name = str(col).strip().lower()
        name = re.sub(r"[^\w]+", "_", name).strip("_") or "unnamed"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        result.append(name)
    return result


# ──────────────────────────────────────────────
# Helper: Resolve Which Columns to Clean
# ──────────────────────────────────────────────

def _resolve_target_cols(
    df: pd.DataFrame,
    numeric_cols: list[str] | None,
    strip_currency: bool,
    strip_commas: bool,
) -> list[str]:
    """Return the caller-supplied column list (validated) or auto-detect via the full cleaning pipeline.

    Auto-detection runs the actual _clean_numeric_series probe on each object column so that
    accounting negatives, percentages, and mixed-currency values are caught — not just bare digits.
    Accepts a column when >50% of non-null values convert successfully.
    """
    if numeric_cols is not None:
        missing = [c for c in numeric_cols if c not in df.columns]
        if missing:
            logger.warning(
                "numeric_cols references columns not in sheet: %s. Available: %s",
                ", ".join(missing),
                ", ".join(df.columns),
            )
        return [c for c in numeric_cols if c in df.columns]

    # Auto-detect using the full cleaning pipeline as a probe.
    candidates = []
    for col in df.select_dtypes(include="object").columns:
        sample = df[col].dropna()
        if sample.empty:
            continue
        cleaned = _clean_numeric_series(sample, strip_currency=strip_currency, strip_commas=strip_commas)
        if cleaned.notna().mean() > 0.5:
            candidates.append(col)
    return candidates


# ──────────────────────────────────────────────
# Helper: Clean a Single Numeric Series
# ──────────────────────────────────────────────

def _clean_numeric_series(
    series: pd.Series,
    strip_currency: bool,
    strip_commas: bool,
) -> pd.Series:
    """Strip formatting characters from a string series and coerce to float. Handles accounting negatives: (1,234) → -1234."""
    s = series.astype(str).str.strip()

    # Accounting-style negatives: (1,234.56) → -1234.56
    s = s.str.replace(r"^\((.+)\)$", r"-\1", regex=True)

    if strip_currency:
        s = s.str.replace(r"[$£€¥]", "", regex=True)

    if strip_commas:
        s = s.str.replace(",", "", regex=False)

    # Remove stray whitespace and percentage signs
    s = s.str.replace(r"[%\s]", "", regex=True)

    # Normalise Excel-style blank representations to NaN
    s = s.replace({"nan": np.nan, "": np.nan, "none": np.nan, "n/a": np.nan, "-": np.nan})

    return pd.to_numeric(s, errors="coerce")


# ──────────────────────────────────────────────
# Helper: Load Summary Logger
# ──────────────────────────────────────────────

def _log_summary(df: pd.DataFrame, path: Path, sheet_name: str | int) -> None:
    """Build the full load-summary report as a single string and emit it at INFO level."""
    total_nulls = int(df.isnull().sum().sum())
    null_cols = df.columns[df.isnull().any()].tolist()

    lines = [
        "=" * 56,
        "  Excel Ingestor — Load Summary",
        "=" * 56,
        f"  File    : {path.name}",
        f"  Sheet   : {sheet_name}",
        f"  Rows    : {len(df):,}",
        f"  Columns : {len(df.columns):,}",
    ]

    null_line = f"  Nulls   : {total_nulls:,} total"
    if null_cols:
        null_line += f"  →  {null_cols}"
    lines.append(null_line)

    lines.append("-" * 56)
    lines.append("  Column dtypes:")
    for col, dtype in df.dtypes.items():
        null_count = int(df[col].isnull().sum())
        flag = f"  ⚠ {null_count} null(s)" if null_count else ""
        # Truncate long column names to keep the summary table readable
        col_display = col if len(col) <= 30 else col[:27] + "..."
        lines.append(f"    {col_display:<30} {str(dtype):<10}{flag}")
    lines.append("=" * 56)

    logger.info("\n".join(lines))


# ──────────────────────────────────────────────
# Helper: Error Handler
# ──────────────────────────────────────────────

def _handle_read_error(exc: Exception, path: Path, sheet_name: str | int) -> NoReturn:
    """Translate pandas / openpyxl exceptions into more actionable errors and always re-raise."""
    msg = str(exc)
    if "Worksheet" in msg or "sheet" in msg.lower():
        raise KeyError(
            f"[ingest_excel] Sheet '{sheet_name}' not found in '{path.name}'.\n"
            "Tip: use pd.ExcelFile(path).sheet_names to list all available sheets."
        ) from exc
    raise RuntimeError(
        f"[ingest_excel] Failed to read '{path.name}': {msg}"
    ) from exc


# ──────────────────────────────────────────────
# CLI Entry Point
# ──────────────────────────────────────────────

_HELP = """
excel_ingestor.py — Command-line usage
---------------------------------------
Load an Excel file and preview the first 10 rows.

Usage:
    python excel_ingestor.py <file>                  Load first sheet
    python excel_ingestor.py <file> <sheet>          Load a named sheet or index
    python excel_ingestor.py --help                  Show this message

Arguments:
    file    Path to the Excel file (.xlsx, .xls, .xlsm, .xlsb)
    sheet   Sheet name (e.g. "Summary") or zero-based index (e.g. 2)
            Defaults to the first sheet if omitted.

Examples:
    python excel_ingestor.py data.xlsx
    python excel_ingestor.py report.xlsx "Q1 Results"
    python excel_ingestor.py export.xlsx 2

Notes:
    - All numeric cleaning options are ON by default (currency, commas, etc.)
    - Column names are auto-sanitised to lowercase with underscores
    - The load summary (shape, dtypes, nulls) prints before the preview
    - To use as a module instead:  from excel_ingestor import ingest_excel
""".strip()


if __name__ == "__main__":
    # Configure a clean handler for CLI use — no timestamp or level prefix,
    # just the message. Only affects runs via `python excel_ingestor.py`;
    # does not interfere with library callers' logging configuration.
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    args = sys.argv[1:]

    if not args or args[0] in ("--help", "-h", "help"):
        print(_HELP)
        sys.exit(0)

    path_arg = args[0]
    # sys.argv values are always str; convert digit strings to int sheet indices.
    sheet_arg: str | int = args[1] if len(args) > 1 else 0
    if isinstance(sheet_arg, str) and sheet_arg.isdigit():
        sheet_arg = int(sheet_arg)

    result = ingest_excel(path_arg, sheet_name=sheet_arg)
    print("\nFirst 10 rows:")
    print(result.head(10).to_string(index=False))
