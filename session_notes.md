# Nexus Consulting Group — monday.com Migration
## Session Notes & Lessons Learned

---

## What Was Built

A two-phase Python migration script that moves a flat Smartsheet CSV export into
a structured monday.com workspace with two linked boards:

- **Nexus - Engagements** (dimension table) — one item per unique engagement
- **Nexus - Deliverables** (fact table) — one item per deliverable row, linked back to its parent engagement

A separate validation script (`validate.py`) queries the migrated boards and
compares them against the source CSV, producing a console report and a
`validation_report.json` artifact.

---

## Architecture Decisions

### Fact / Dimension Model
The source CSV is denormalized — engagement metadata is repeated on every
deliverable row. The migration restructures this into:
- A **dimension board** (Engagements) with one stable record per engagement
- A **fact board** (Deliverables) with transactional work items and a foreign key
  back to the dimension via a Connect Boards column

### Two-Phase Migration
Phase 1 and Phase 2 were split after discovering that Connect Boards columns
cannot be created programmatically (see API Limitations below). This required
a manual step between phases.

| Phase | Command | What it does |
|-------|---------|--------------|
| 1 | `python migration.py --phase 1` | Creates boards and columns, writes `board_config.json` |
| — | Manual step in monday UI | Add Connect Boards column, link to Engagements board |
| 2 | `python migration.py --phase 2` | Loads all data into existing boards |

### Incremental Config Write
`board_config.json` is written after each board is created (not at the very end)
so that a mid-run failure leaves the IDs of already-created boards on disk.
Without this, a crash during column creation would orphan boards in monday with
no record of their IDs.

---

## Issues Encountered

### 1. Invalid `ColumnType` enum: `connect_boards`
**Error:** `400 Bad Request`
**Cause:** The initial column type string `"connect_boards"` is not a valid
`ColumnType` enum value.
**Fix:** Changed to `"board_relation"` — the correct monday API enum value.

### 2. `board_relation` columns cannot be created via the API
**Error:** `GraphQL error: This column type is not supported yet in the API`
**Cause:** monday's API explicitly does not support creating Connect Boards
columns programmatically.
**Reference:** https://developer.monday.com/api-reference/reference/connect
**Fix:** Removed `board_relation` from Phase 1. The column is added manually
in the UI, and Phase 2 queries the board at runtime to find it by type
automatically using `get_board_relation_column()`.

### 3. 429 Too Many Requests
**Error:** `HTTPError: 429 Client Error: Too Many Requests`
**Cause:** monday uses complexity-based rate limiting. Creating ~15 columns
in quick succession exceeded the budget.
**Fix:** Added exponential backoff retry logic to `run_query()` in both scripts
(10s → 20s → 40s), and increased the baseline delay between calls from 0.35s
to 0.5s. Also ported the same retry logic to `validate.py`.

### 4. Status labels don't exist by default
**Error:** `GraphQL error: This status label doesn't exist, possible statuses are: {0: Working on it, 1: Done, 2: Stuck}`
**Cause:** monday creates status columns with default labels. Attempting to set
a custom label like "Active" fails if it hasn't been defined on that column yet.
**Fix:** Added `create_labels_if_missing: true` to the `create_item` mutation,
which creates the label automatically on first use.

### 5. `board_config.json` not written after failed runs
**Cause:** The config write was at the very end of `phase_1()`. Any exception
before that point (e.g., the rate limit crash on the last column) left boards
created in monday with no record of their IDs.
**Fix:** Config is now written incrementally — once after the Engagements board
is set up, and again after Deliverables. A failed run leaves whatever was
completed on disk.

### 6. Duplicate boards on re-run
**Cause:** Re-running Phase 1 after a failed attempt created new boards alongside
the partially-created ones from the previous run.
**Fix:** Phase 1 now checks for `board_config.json` at startup and exits with
an error if it already exists, preventing duplicate board creation.

### 7. `int()` cast on item IDs for Connect Boards column
**Cause:** Item IDs returned by the monday API are strings. Casting them to
`int()` when building the `board_relation` column value caused a type mismatch.
**Fix:** Removed the `int()` cast — IDs are passed as strings.

### 8. Orphaned deliverables false positive in validation
**Cause:** `board_relation` columns do not populate the standard `text` or
`value` fields in a GraphQL `column_values` response. The `col_has_value()`
check saw both as empty and flagged all deliverables as orphans, even though
the links were visible in the monday UI.
**Fix:** Updated `fetch_board_items()` to use a GraphQL inline fragment
(`... on BoardRelationValue { linked_items { id } }`) and updated
`col_has_value()` to check `linked_items` for board_relation columns.

### 9. Default "Task 1" placeholder item on new boards
**Cause:** monday creates a default item on every new board.
**Fix:** Added `empty: true` to the `create_board` mutation, which suppresses
the default item.

### 10. Name column labeled "Item" instead of "Engagement Name"
**Cause:** monday's built-in name column label reflects the board's item
nickname, which defaults to "Item".
**Note:** This is a cosmetic UI issue — data is correct. Renamed manually via
the column header in the monday UI. Could be automated with a
`change_column_title` API call in a future iteration.

---

## API Limitations (monday.com)

| Limitation | Reference |
|-----------|-----------|
| `board_relation` (Connect Boards) columns cannot be created via the API | https://developer.monday.com/api-reference/reference/connect |
| Boards must be connected in the UI before items can be linked | https://developer.monday.com/api-reference/reference/connect |
| Status column labels must exist before they can be set (or use `create_labels_if_missing: true`) | — |
| Rate limiting is complexity-based, not just request count | — |

---

## Validation Results

All 8 checks passed after fixes:

| Check | Result |
|-------|--------|
| Engagement count (expected 6, got 6) | PASS |
| Deliverable count (expected 27, got 27) | PASS |
| All engagement IDs present | PASS |
| All deliverable IDs present | PASS |
| No orphaned deliverables | PASS |
| Required deliverable fields populated | PASS |
| Engagement status normalization | PASS |
| Deliverable status normalization | PASS |

---

## Files

| File | Purpose |
|------|---------|
| `migration.py` | Two-phase migration script |
| `validate.py` | Post-migration validation script |
| `board_config.json` | Board/column IDs written by Phase 1, read by Phase 2 and validate.py |
| `nexus_smartsheet_export.csv` | Source data (read-only, never modified) |
| `validation_report.json` | Full validation output written by validate.py |
| `.env` | `MONDAY_API_TOKEN` (not committed to repo) |
