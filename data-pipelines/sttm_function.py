#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Jul 29 06:22:00 2025

@author: skirk
"""

import re
import pandas as pd

def extract_sttm(script_text: str, filename: str = None) -> pd.DataFrame:
    """
    Scans embedded SQL in a Python script and returns a deduplicated,
    sorted DataFrame showing source-to-target lineage:
    [Database, Table, Column], optionally including SQL and filename.

    Args:
        script_text (str): Full Python code (as a string).
        filename (str, optional): Name of the script for reference in results.

    Returns:
        pd.DataFrame: Structured STTM mappings from all detected SQL blocks.
        
    Example Usage:
        from sharedfunctions import extract_sttm

        my_code = 
        query1 = \"\"\"SELECT t.TRANS_ID FROM BMGPDD.ALLTRANS_TABLE t\"\"\"
        query2 = \"\"\"SELECT dd1.CUST_NUM FROM CIS.CUST_DEMO JOIN BMGPDD.ALLTRANS_TABLE ON dd1.ID = t.ID\"\"\"
        
        sttm_df = extract_sttm(my_code, filename="project_in_progress.py")
        print(sttm_df)
    """

    def extract_sql_blocks(script: str) -> list:
        """
        Identifies SQL queries inside quoted Python strings.

        Args:
            script (str): Raw Python code.

        Returns:
            list: List of candidate SQL query strings.
        """
        try:
            string_blocks = re.findall(
                r"(\"\"\".*?\"\"\"|'''.*?'''|\".*?\"|'.*?')",
                script, re.DOTALL
            )
            sql_candidates = []
            for block in string_blocks:
                stripped = block.strip("\"' \n")
                if re.search(r"\bSELECT\b", stripped, re.IGNORECASE) and re.search(r"\bFROM\b", stripped, re.IGNORECASE):
                    sql_candidates.append(stripped)
            return sql_candidates
        except Exception as e:
            print(f"[SQL Extraction Error] {e}")
            return []

    def extract_sttm_from_sql(sql_text: str) -> pd.DataFrame:
        """
        Parses one SQL query string for source lineage.

        Args:
            sql_text (str): SQL code.

        Returns:
            pd.DataFrame: Extracted mappings from the query.
        """
        try:
            sql = sql_text.replace("\n", " ").strip()

            table_pattern = r"(?:FROM|JOIN)\s+([A-Z0-9_]+)\.([A-Z0-9_]+)"
            tables = re.findall(table_pattern, sql, re.IGNORECASE)

            column_pattern = r"SELECT\s+(.*?)\s+FROM"
            col_section = re.search(column_pattern, sql, re.IGNORECASE)
            raw_columns = col_section.group(1).split(",") if col_section else []

            columns = []
            for col in raw_columns:
                col = col.strip()
                parts = col.split(".")
                if len(parts) == 2:
                    columns.append((parts[0], parts[1]))  # qualified
                else:
                    columns.append(("", parts[0]))        # unqualified

            data = []
            for db, tbl in tables:
                for _, col in columns:
                    data.append({
                        "Database": db,
                        "Table": tbl,
                        "Column": col,
                        "SQL": sql_text,
                        "Filename": filename if filename else "inline"
                    })

            return pd.DataFrame(data)

        except Exception as e:
            print(f"[STTM Parse Error] {e}")
            return pd.DataFrame(columns=["Database", "Table", "Column", "SQL", "Filename"])

    # Extract and parse
    try:
        sql_blocks = extract_sql_blocks(script_text)
        all_frames = [extract_sttm_from_sql(sql) for sql in sql_blocks if sql]

        if not all_frames:
            return pd.DataFrame(columns=["Database", "Table", "Column", "SQL", "Filename"])

        final_df = (
            pd.concat(all_frames, ignore_index=True)
            .drop_duplicates()
            .sort_values(by=["Database", "Table", "Column"])
            .reset_index(drop=True)
        )
        return final_df

    except Exception as e:
        print(f"[STTM Function Error] {e}")
        return pd.DataFrame(columns=["Database", "Table", "Column", "SQL", "Filename"])
