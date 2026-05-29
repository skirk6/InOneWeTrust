-- =============================================================================
-- fuzzy_name_match.sql
-- Fuzzy name matching: upstream FULL_NAME vs target FIRST / MIDDLE / LAST NAME
--
-- Use case: Given a watchlist or upstream feed of full names, identify potential
-- matches in a customer table where names may differ due to misspellings,
-- nicknames, missing middle names, or data entry inconsistencies.
--
-- Matching approach (no TD_SIMILARITY license required):
--   1. Normalize both sides  -- UPPER, TRIM, strip punctuation, collapse spaces
--   2. Token extraction      -- STRTOK pulls first / last tokens from FULL_NAME
--   3. Score each pair       -- exact match > phonetic (SOUNDEX) fallback
--   4. Filter early          -- discard pairs below threshold inside scored CTE
--
-- Score guide:
--   100  Exact normalized full name match
--   100  Both first + last tokens exact (2-token upstream name only)
--    90  Both first + last tokens exact (3+ token upstream — middle not verified)
--    85  Last name exact  +  first name SOUNDEX (phonetic) match
--    80  Last name SOUNDEX match  +  first name exact
--    70  Last name exact only (weakest retained match — possible name change)
--     0  No meaningful match — excluded by threshold
--
-- SOUNDEX: Teradata built-in phonetic algorithm. Converts a name to a 4-char
-- code based on sound, not spelling (e.g. SMITH and SMYTH both return S530).
-- Useful for catching misspellings and variant spellings of English names.
-- Not reliable for non-English names.
--
-- Threshold: 70 (adjust in the WHERE clause at the bottom of scored CTE)
--
-- Performance note: The CROSS JOIN in scored is intentional — every upstream
-- name must be compared to every customer. For large customer tables, run
-- EXPLAIN before production use; look for "product join" in the plan and review
-- the estimated spool row count for the scored step.
--
-- Hyphen note: Hyphens in surnames are replaced with a space (DE-SOUZA →
-- DE SOUZA), so last_token captures only the post-hyphen fragment (SOUZA).
-- For compound last names, change the hyphen OREPLACE to remove rather than
-- split: OREPLACE(FULL_NAME, '-', '') → DE-SOUZA becomes DESOUZA.
--
-- Placeholder names — swap these for your environment:
--   upstream_watchlist  -- source table containing SUBJECT_ID, FULL_NAME
--   customer_table      -- target table containing CUSTOMER_ID, FIRST_NAME,
--                          MIDDLE_NAME, LAST_NAME
-- =============================================================================

WITH upstream_normalized AS (

    -- Strip punctuation and normalize case. Four OREPLACE passes:
    --   1. Remove periods        Dr. SMITH  → DR SMITH
    --   2. Remove commas         SMITH, J   → SMITH  J  (double space — fixed by pass 4)
    --   3. Replace hyphens       MARY-JANE  → MARY JANE
    --   4. Collapse double space SMITH  J   → SMITH J
    SELECT
        SUBJECT_ID,
        FULL_NAME,
        UPPER(TRIM(
            OREPLACE(
            OREPLACE(
            OREPLACE(
            OREPLACE(FULL_NAME, '.', ''),
                     ',', ''),
                     '-', ' '),
                     '  ', ' ')   -- collapse double spaces introduced by comma/hyphen removal
        )) AS name_clean
    FROM upstream_watchlist

),

upstream_tokens AS (

    -- Extract first and last tokens from the normalized full name.
    -- STRTOK(string, delimiter, n) returns the nth space-delimited token.
    -- Last token position = number of spaces + 1.
    -- NULLIF guards against empty string tokens (from any residual consecutive
    -- spaces) which would cause SOUNDEX('') = SOUNDEX('') false matches.
    SELECT
        SUBJECT_ID,
        FULL_NAME,
        name_clean,
        NULLIF(STRTOK(name_clean, ' ', 1), '')                     AS first_token,
        NULLIF(
            STRTOK(name_clean, ' ',
                CHARACTERS(name_clean)
                - CHARACTERS(OREPLACE(name_clean, ' ', ''))
                + 1
            ), ''
        )                                                           AS last_token,
        -- Token count distinguishes "JOHN SMITH" (2) from "JOHN PAUL SMITH" (3+)
        -- Used to avoid scoring a 3-token upstream name as 100 when the middle
        -- token was never checked against the customer record.
        CHARACTERS(name_clean)
        - CHARACTERS(OREPLACE(name_clean, ' ', ''))
        + 1                                                         AS token_count
    FROM upstream_normalized

),

target_normalized AS (

    -- Build comparable name forms from split columns.
    -- COALESCE guards against NULL FIRST_NAME or LAST_NAME — without it,
    -- string concatenation returns NULL for the entire expression and the
    -- customer silently scores 0 and drops from all results.
    -- Note: customers with blank (non-NULL but whitespace-only) names are also
    -- excluded. To diagnose suppressed records before running:
    --   SELECT COUNT(*) FROM customer_table WHERE TRIM(COALESCE(LAST_NAME,'')) = ''
    SELECT
        CUSTOMER_ID,
        FIRST_NAME,
        MIDDLE_NAME,
        LAST_NAME,
        UPPER(TRIM(COALESCE(FIRST_NAME, ''))) AS first_clean,
        UPPER(TRIM(COALESCE(LAST_NAME,  ''))) AS last_clean,
        -- full_no_middle: matches upstream names that omit the customer's middle
        -- name (e.g. upstream "JOHN SMITH" matching customer "JOHN PAUL SMITH")
        UPPER(TRIM(COALESCE(FIRST_NAME, ''))
              || ' ' || TRIM(COALESCE(LAST_NAME, '')))              AS full_no_middle,
        CASE
            WHEN MIDDLE_NAME IS NULL OR TRIM(MIDDLE_NAME) = ''
            THEN UPPER(TRIM(COALESCE(FIRST_NAME, ''))
                       || ' ' || TRIM(COALESCE(LAST_NAME, '')))
            ELSE UPPER(TRIM(COALESCE(FIRST_NAME, ''))
                       || ' ' || TRIM(MIDDLE_NAME)
                       || ' ' || TRIM(COALESCE(LAST_NAME, '')))
        END                                                         AS full_with_middle
    FROM customer_table

),

scored AS (

    -- Wrap the CROSS JOIN in a subquery and filter here so the optimizer can
    -- eliminate non-matching pairs before spool materialization rather than
    -- writing all N_upstream x N_customer rows and filtering after.
    SELECT *
    FROM (
        SELECT
            u.SUBJECT_ID,
            u.FULL_NAME,
            t.CUSTOMER_ID,
            t.FIRST_NAME,
            t.MIDDLE_NAME,
            t.LAST_NAME,
            CASE
                -- Exact full name match (with or without middle name on record)
                WHEN u.name_clean IN (t.full_no_middle, t.full_with_middle)
                    THEN 100

                -- Both first and last tokens match exactly.
                -- 2-token upstream (FIRST LAST only): full match confirmed → 100
                -- 3+ token upstream: middle name(s) unverified → 90
                WHEN u.last_token  = t.last_clean
                 AND u.first_token = t.first_clean
                    THEN CASE WHEN u.token_count = 2 THEN 100 ELSE 90 END

                -- Last name exact; first name sounds alike (e.g. JOHN / JON)
                -- NULL / empty token guards prevent SOUNDEX('') false matches
                WHEN u.last_token = t.last_clean
                 AND u.first_token IS NOT NULL AND u.first_token <> ''
                 AND t.first_clean <> ''
                 AND SOUNDEX(u.first_token) = SOUNDEX(t.first_clean)
                    THEN 85

                -- Last name sounds alike; first name exact (e.g. SMITH / SMYTH)
                WHEN u.last_token IS NOT NULL AND u.last_token <> ''
                 AND t.last_clean <> ''
                 AND SOUNDEX(u.last_token) = SOUNDEX(t.last_clean)
                 AND u.first_token = t.first_clean
                    THEN 80

                -- Last name exact only; possible name change or maiden name.
                -- Weakest retained score — sits on the default threshold boundary.
                WHEN u.last_token = t.last_clean
                    THEN 70

                ELSE 0
            END AS match_score
        FROM upstream_tokens  u
        CROSS JOIN target_normalized t
    ) cross_scored
    WHERE match_score >= 70  -- threshold: 70=default; raise for fewer/stronger matches

)

-- =============================================================================
-- Final output: one row per upstream/target pair at or above the threshold.
-- Ordered by subject then descending score so the strongest match appears first.
-- =============================================================================
SELECT
    SUBJECT_ID,
    FULL_NAME                                               AS upstream_name,
    CUSTOMER_ID,
    TRIM(COALESCE(FIRST_NAME, ''))
        || CASE
               WHEN MIDDLE_NAME IS NULL OR TRIM(MIDDLE_NAME) = '' THEN ''
               ELSE ' ' || TRIM(MIDDLE_NAME)
           END
        || ' ' || TRIM(COALESCE(LAST_NAME, ''))            AS target_name,
    match_score                                             AS match_pct
FROM scored
ORDER BY SUBJECT_ID, match_score DESC;
