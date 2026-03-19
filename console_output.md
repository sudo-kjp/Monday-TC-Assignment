# Console Output Log
## Nexus Consulting Group — monday.com Migration

---

## Phase 1 — Run 1 (Failed: invalid ColumnType `connect_boards`)

```
(base) kjp@Kevins-MacBook-Air Monday.com % python migration.py --phase 1
============================================================
  Nexus Consulting Group — monday.com Migration
============================================================

[Phase 1] Creating boards and columns...

[Step 1/4] Creating Engagements board (dimension)...
  ✓ Board created: 'Nexus - Engagements' (id: 18404633787)
    + Engagement ID (text) → text_mm1kye81
    + Client (text) → text_mm1k324a
    + Engagement Lead (text) → text_mm1k9mr0
    + Engagement Start (date) → date_mm1kbg67
    + Engagement End (date) → date_mm1kvb8k
    + Budget (numbers) → numeric_mm1kqrzb
    + Engagement Status (status) → color_mm1k3ng0

[Step 2/4] Creating Deliverables board (fact)...
  ✓ Board created: 'Nexus - Deliverables' (id: 18404633819)
    + Deliverable ID (text) → text_mm1k8x4y
    + Assignee (text) → text_mm1kjg2k
    + Due Date (date) → date_mm1kav2
    + Priority (status) → color_mm1k15wy
    + Deliverable Status (status) → color_mm1k774q
    + Hours Estimated (numbers) → numeric_mm1kyfx
Traceback (most recent call last):
  File "/Users/kjp/My Drive/Career/Side Projects/Job Applications/Monday.com/migration.py", line 446, in <module>
    main()
  File "/Users/kjp/My Drive/Career/Side Projects/Job Applications/Monday.com/migration.py", line 440, in main
    phase_1()
  File "/Users/kjp/My Drive/Career/Side Projects/Job Applications/Monday.com/migration.py", line 360, in phase_1
    del_board_id, del_cols = setup_deliverables_board()
  File "/Users/kjp/My Drive/Career/Side Projects/Job Applications/Monday.com/migration.py", line 244, in setup_deliverables_board
    "engagement": create_column(board_id, "Engagement", "connect_boards"),
  File "/Users/kjp/My Drive/Career/Side Projects/Job Applications/Monday.com/migration.py", line 204, in create_column
    data = query_with_delay(query, {"boardId": board_id, "title": title, "type": col_type})
requests.exceptions.HTTPError: 400 Client Error: Bad Request for url: https://api.monday.com/v2
```

**Root cause:** `"connect_boards"` is not a valid `ColumnType` enum value.
**Fix:** Changed to `"board_relation"`.

---

## Phase 1 — Run 2 (Failed: 429 rate limit on `board_relation`)

```
(base) kjp@Kevins-MacBook-Air Monday.com % python migration.py --phase 1
============================================================
  Nexus Consulting Group — monday.com Migration
============================================================

[Phase 1] Creating boards and columns...

[Step 1/4] Creating Engagements board (dimension)...
  ✓ Board created: 'Nexus - Engagements' (id: 18404642684)
    + Engagement ID (text) → text_mm1kgdcw
    + Client (text) → text_mm1kstx2
    + Engagement Lead (text) → text_mm1kezar
    + Engagement Start (date) → date_mm1k3ssw
    + Engagement End (date) → date_mm1kbpp3
    + Budget (numbers) → numeric_mm1kjkaq
    + Engagement Status (status) → color_mm1knbyt

[Step 2/4] Creating Deliverables board (fact)...
  ✓ Board created: 'Nexus - Deliverables' (id: 18404642713)
    + Deliverable ID (text) → text_mm1kdbce
    + Assignee (text) → text_mm1k7k1t
    + Due Date (date) → date_mm1knjv1
    + Priority (status) → color_mm1kxnf4
    + Deliverable Status (status) → color_mm1k7w2n
    + Hours Estimated (numbers) → numeric_mm1k16rw
Traceback (most recent call last):
  ...
requests.exceptions.HTTPError: 429 Client Error: Too Many Requests for url: https://api.monday.com/v2
```

**Root cause:** Rate limit hit on the `board_relation` column creation attempt.
**Fix:** Added exponential backoff retry logic (10s → 20s → 40s).

---

## Phase 1 — Run 3 (Failed: `board_relation` unsupported via API)

```
(base) kjp@Kevins-MacBook-Air Monday.com % python migration.py --phase 1
============================================================
  Nexus Consulting Group — monday.com Migration
============================================================

[Phase 1] Creating boards and columns...

[Step 1/4] Creating Engagements board (dimension)...
  ✓ Board created: 'Nexus - Engagements' (id: 18404643706)
    + Engagement ID (text) → text_mm1k1hfq
    + Client (text) → text_mm1k2n2n
    + Engagement Lead (text) → text_mm1kb5nt
    + Engagement Start (date) → date_mm1k564c
    + Engagement End (date) → date_mm1kygdh
    + Budget (numbers) → numeric_mm1k7623
    + Engagement Status (status) → color_mm1kgsag

[Step 2/4] Creating Deliverables board (fact)...
  ✓ Board created: 'Nexus - Deliverables' (id: 18404643765)
    + Deliverable ID (text) → text_mm1kdk93
    + Assignee (text) → text_mm1knnv3
    + Due Date (date) → date_mm1k73ye
    + Priority (status) → color_mm1kr9f8
    + Deliverable Status (status) → color_mm1kq9tx
    + Hours Estimated (numbers) → numeric_mm1ktcft
  Rate limited — waiting 10s before retry 1/3...
  Rate limited — waiting 20s before retry 2/3...
  Rate limited — waiting 40s before retry 3/3...
Exception: GraphQL error: [{'message': 'This column type is not supported yet in the API', 'extensions': {'code': 'InvalidColumnTypeException', 'error_data': {'actual_type': 'board-relation'}}}]
```

**Root cause:** `board_relation` columns cannot be created via the API at all.
**Fix:** Removed `board_relation` from Phase 1. Column is added manually in the monday UI. Phase 2 discovers it at runtime via `get_board_relation_column()`.

---

## Phase 2 — Run 1 (Failed: missing `board_config.json`)

```
(base) kjp@Kevins-MacBook-Air Monday.com % python migration.py --phase 2
============================================================
  Nexus Consulting Group — monday.com Migration
============================================================
Error: board_config.json not found. Run Phase 1 first.
```

**Root cause:** Phase 1 never completed successfully so `board_config.json` was never written.
**Fix:** Config is now written incrementally after each board is created.

---

## Phase 1 — Run 4 (Success)

```
(base) kjp@Kevins-MacBook-Air Monday.com % python migration.py --phase 1
============================================================
  Nexus Consulting Group — monday.com Migration
============================================================

[Phase 1] Creating boards and columns...

[Step 1/4] Creating Engagements board (dimension)...
  ✓ Board created: 'Nexus - Engagements' (id: 18404650148)
    + Engagement ID (text) → text_mm1k49e8
    + Client (text) → text_mm1kaw6d
    + Engagement Lead (text) → text_mm1kmzr2
    + Engagement Start (date) → date_mm1ktan
    + Engagement End (date) → date_mm1kz0j7
    + Budget (numbers) → numeric_mm1k421g
    + Engagement Status (status) → color_mm1kaevw

[Step 2/4] Creating Deliverables board (fact)...
  ✓ Board created: 'Nexus - Deliverables' (id: 18404650197)
    + Deliverable ID (text) → text_mm1km0ga
    + Assignee (text) → text_mm1k7gew
    + Due Date (date) → date_mm1k2m9f
    + Priority (status) → color_mm1k1ves
    + Deliverable Status (status) → color_mm1k194c
    + Hours Estimated (numbers) → numeric_mm1kc33s

============================================================
  Phase 1 Complete — Action Required
============================================================
  Board IDs saved to : board_config.json

  Before running Phase 2, do the following in monday.com:
  1. Open 'Nexus - Deliverables'
  2. Add a Connect Boards column (+) and name it 'Engagement'
  3. Link it to 'Nexus - Engagements'
  (The API cannot create this column type — it must be done in the UI)

  Then run:  python migration.py --phase 2
============================================================
```

---

## Phase 2 — Run 2 (Failed: status label doesn't exist)

```
(base) kjp@Kevins-MacBook-Air Monday.com % python migration.py --phase 2
============================================================
  Nexus Consulting Group — monday.com Migration
============================================================

[Phase 2] Looking for Connect Boards column on Deliverables board...
  ✓ Found Connect Boards column: 'Engagement' → board_relation_mm1k3t7n

Source: 27 deliverable rows → 6 unique engagements

[Phase 2] Loading data into existing boards...

[Step 3/4] Loading 6 engagements...
Exception: GraphQL error: [{'message': "This status label doesn't exist, possible statuses are: {0: Working on it, 1: Done, 2: Stuck}", 'extensions': {'code': 'ColumnValueException', 'error_data': {'column_name': 'Engagement Status', 'column_value': '{"label" => "Active"}'}}}]
```

**Root cause:** Status columns are created with monday's default labels. Custom labels ("Active", "Complete", etc.) don't exist until created.
**Fix:** Added `create_labels_if_missing: true` to the `create_item` mutation.

---

## Phase 2 — Run 3 (Success)

```
(base) kjp@Kevins-MacBook-Air Monday.com % python migration.py --phase 2
============================================================
  Nexus Consulting Group — monday.com Migration
============================================================

[Phase 2] Looking for Connect Boards column on Deliverables board...
  ✓ Found Connect Boards column: 'Engagement' → board_relation_mm1k3t7n

Source: 27 deliverable rows → 6 unique engagements

[Phase 2] Loading data into existing boards...

[Step 3/4] Loading 6 engagements...
  ✓ Digital Transformation Strategy ['In Progress' → 'Active'] → item 11549279600
  ✓ Operational Excellence Program ['Active'] → item 11549351357
  ✓ Market Entry Analysis ['In Progress' → 'Active'] → item 11549278257
  ✓ Supply Chain Optimization ['Complete'] → item 11549287402
  ✓ Customer Experience Redesign ['On Hold'] → item 11549289894
  ✓ Workforce Planning Initiative ['Not Started'] → item 11549278052

[Step 4/4] Loading 27 deliverables...
  ✓ Current State Assessment ['Done'] → item 11549272092
  ✓ Stakeholder Interviews ['Done'] → item 11549351855
  ✓ Technology Roadmap ['Working on it' → 'In Progress'] → item 11549353311
  ✓ Implementation Plan ['To Do'] → item 11549295563
  ✓ Executive Presentation ['Not Started' → 'To Do'] → item 11549272145
  ✓ Process Mapping Workshop ['Done'] → item 11549277976
  ✓ Efficiency Analysis Report ['In Review'] → item 11549288000
  ✓ KPI Dashboard Design ['In Progress'] → item 11549310620
  ✓ Training Materials ['To Do'] → item 11549277717
  ✓ Change Management Plan ['To Do'] → item 11549287560
  ✓ Competitive Landscape Review ['Done'] → item 11549281495
  ✓ Customer Segmentation Study ['Working on it' → 'In Progress'] → item 11549299801
  ✓ Go-to-Market Strategy ['Not Started' → 'To Do'] → item 11549283896
  ✓ Financial Projections ['To Do'] → item 11549283189
  ✓ Inventory Analysis ['Done'] → item 11549277840
  ✓ Vendor Assessment ['Done'] → item 11549288220
  ✓ Logistics Redesign ['Done'] → item 11549312814
  ✓ Implementation Roadmap ['Done'] → item 11549296376
  ✓ Final Report & Handoff ['Done'] → item 11549293232
  ✓ Journey Mapping Sessions ['Done'] → item 11549311405
  ✓ Pain Point Analysis ['Done'] → item 11549280429
  ✓ Service Blueprint ['In Progress'] → item 11549296508
  ✓ Prototype Development ['To Do'] → item 11549299811
  ✓ Skills Gap Assessment ['To Do'] → item 11549298998
  ✓ Hiring Strategy Document ['To Do'] → item 11549293527
  ✓ Training Program Design ['To Do'] → item 11549308795
  ✓ Succession Planning Framework ['To Do'] → item 11549311255

============================================================
  Migration Complete
============================================================
  Engagements loaded : 6
  Deliverables loaded: 27
============================================================
```

---

## Validation — Run 1 (Failed: orphaned deliverables false positive)

```
(base) kjp@Kevins-MacBook-Air Monday.com % python validate.py
...
  Result: 7/8 checks passed  (1 failed)
  [FAIL] ✗ No orphaned deliverables (all linked to an engagement)
          → 27 orphan(s) found
```

**Root cause:** `board_relation` columns don't populate `text` or `value` in the standard GraphQL `column_values` response. Linked items are only accessible via a `BoardRelationValue` inline fragment (`linked_items { id }`).
**Fix:** Updated `fetch_board_items` query to use inline fragment; updated `col_has_value` to check `linked_items`.

---

## Validation — Run 2 (Failed: 429 before retry logic was added)

```
(base) kjp@Kevins-MacBook-Air Monday.com % python validate.py
...
Fetching monday.com board data...
requests.exceptions.HTTPError: 429 Client Error: Too Many Requests for url: https://api.monday.com/v2
```

**Fix:** Ported retry logic from `migration.py` into `validate.py`.

---

## Validation — Run 3 (Success: 8/8 checks passed)

```
(base) kjp@Kevins-MacBook-Air Monday.com % python validate.py
============================================================
  Nexus Consulting Group — Migration Validation
============================================================

Loading source CSV...
  Source: 27 deliverables, 6 engagements

Fetching monday.com board data...
  Rate limited — waiting 10s before retry 1/3...
  Rate limited — waiting 20s before retry 2/3...
  Rate limited — waiting 40s before retry 3/3...
  monday: 27 deliverables, 6 engagements

Running validation checks...

============================================================
  MIGRATION VALIDATION REPORT
  Nexus Consulting Group → monday.com
  Generated: 2026-03-19 14:20:05
============================================================

  Result: 8/8 checks passed ✓

  ──────────────────────────────────────────────────────
  COUNT CHECKS
  ──────────────────────────────────────────────────────
  [PASS] ✓ Engagement count: expected 6, got 6
  [PASS] ✓ Deliverable count: expected 27, got 27

  ──────────────────────────────────────────────────────
  DATA INTEGRITY CHECKS
  ──────────────────────────────────────────────────────
  [PASS] ✓ All engagement IDs present
  [PASS] ✓ All deliverable IDs present
  [PASS] ✓ No orphaned deliverables (all linked to an engagement)
  [PASS] ✓ Required deliverable fields populated (assignee, due date, hours)

  ──────────────────────────────────────────────────────
  STATUS NORMALIZATION — ENGAGEMENT
  ──────────────────────────────────────────────────────
  [PASS] ✓ Engagement status normalization (raw CSV → monday value)

    ✓  Digital Transformation Strat  'In Progress' → 'Active'
    ✓  Operational Excellence Progr  'Active' (no change)
    ✓  Market Entry Analysis         'In Progress' → 'Active'
    ✓  Supply Chain Optimization     'Complete' (no change)
    ✓  Customer Experience Redesign  'On Hold' (no change)
    ✓  Workforce Planning Initiativ  'Not Started' (no change)

  ──────────────────────────────────────────────────────
  STATUS NORMALIZATION — DELIVERABLES
  ──────────────────────────────────────────────────────
  [PASS] ✓ Deliverable status normalization (raw CSV → monday value)

    ✓  Current State Assessment          'Done' (no change)
    ✓  Stakeholder Interviews            'Done' (no change)
    ✓  Technology Roadmap                'Working on it' → 'In Progress'
    ✓  Implementation Plan               'To Do' (no change)
    ✓  Executive Presentation            'Not Started' → 'To Do'
    ✓  Process Mapping Workshop          'Done' (no change)
    ✓  Efficiency Analysis Report        'In Review' (no change)
    ✓  KPI Dashboard Design              'In Progress' (no change)
    ✓  Training Materials                'To Do' (no change)
    ✓  Change Management Plan            'To Do' (no change)
    ✓  Competitive Landscape Review      'Done' (no change)
    ✓  Customer Segmentation Study       'Working on it' → 'In Progress'
    ✓  Go-to-Market Strategy             'Not Started' → 'To Do'
    ✓  Financial Projections             'To Do' (no change)
    ✓  Inventory Analysis                'Done' (no change)
    ✓  Vendor Assessment                 'Done' (no change)
    ✓  Logistics Redesign                'Done' (no change)
    ✓  Implementation Roadmap            'Done' (no change)
    ✓  Final Report & Handoff            'Done' (no change)
    ✓  Journey Mapping Sessions          'Done' (no change)
    ✓  Pain Point Analysis               'Done' (no change)
    ✓  Service Blueprint                 'In Progress' (no change)
    ✓  Prototype Development             'To Do' (no change)
    ✓  Skills Gap Assessment             'To Do' (no change)
    ✓  Hiring Strategy Document          'To Do' (no change)
    ✓  Training Program Design           'To Do' (no change)
    ✓  Succession Planning Framework     'To Do' (no change)

============================================================
  ✓ ALL CHECKS PASSED — Migration looks good
============================================================

  Full report written to: validation_report.json
```
