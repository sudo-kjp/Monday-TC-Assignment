"""
migration.py
Nexus Consulting Group — Smartsheet → monday.com Migration

Design:
  The source CSV is a denormalized flat file — one row per deliverable with
  engagement-level metadata repeated on every row. This script restructures
  the data into a fact/dimension model across two monday.com boards:

    Dimension board → Nexus - Engagements
      Descriptive master data: client, lead, budget, start/end dates, status.
      One record per engagement. Relatively stable — changes infrequently.

    Fact board → Nexus - Deliverables
      Transactional work items with a measurable attribute (hours estimated)
      and a foreign key relationship back to the dimension (Connect Boards).
      One record per deliverable row in the source CSV.

  Status values are normalized as part of the migration per discovery call
  requirements. Raw source values are preserved in board_config.json so
  validate.py can audit each transformation.

Assumptions documented:
  - engagement_id / deliverable_id stored as text columns for cross-referencing
  - Assignees stored as text (names only in source; monday People column requires
    provisioned account users — coordinate with IT for a production migration)
  - Budget stored as a numbers column; monday handles currency formatting
  - Dates converted from MM/DD/YYYY (Smartsheet) to YYYY-MM-DD (monday API)
  - start_date / end_date are engagement-level only; deliverables have due_date only
  - Source CSV is treated as immutable — never written to or modified

Requirements: pip install requests python-dotenv
Usage:        python migration.py
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────────────
API_TOKEN     = os.getenv("MONDAY_API_TOKEN")
API_URL       = "https://api.monday.com/v2"
HEADERS       = {
    "Authorization": API_TOKEN,
    "Content-Type":  "application/json",
    "API-Version":   "2024-01",
}
CSV_PATH      = "nexus_smartsheet_export.csv"
CONFIG_OUTPUT = "board_config.json"

# ── Status normalization ──────────────────────────────────────────────────────
# Every key maps a raw CSV value (lowercased) to a canonical monday label.
# Discovery call: engagement and deliverable statuses are kept explicitly distinct.

ENGAGEMENT_STATUS_MAP = {
    "in progress": "Active",      # Derek: "In Progress" and "Active" mean the same thing
    "active":      "Active",
    "complete":    "Complete",    # Priya: "Complete" and "Done" used interchangeably
    "done":        "Complete",
    "on hold":     "On Hold",
    "not started": "Not Started",
}

DELIVERABLE_STATUS_MAP = {
    "to do":         "To Do",        # Derek: "To Do" and "Not Started" are the same stage
    "not started":   "To Do",
    "in progress":   "In Progress",  # Derek: "Working on it" = "In Progress"
    "working on it": "In Progress",
    "in review":     "In Review",
    "done":          "Done",
}

# ── API helpers ───────────────────────────────────────────────────────────────

def run_query(query: str, variables: dict = None, retries: int = 3) -> dict:
    """Execute a GraphQL query/mutation against the monday.com API.

    Retries up to `retries` times on 429 rate-limit responses, backing off
    exponentially (10s, 20s, 40s) before each retry.
    """
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    for attempt in range(1, retries + 2):
        response = requests.post(API_URL, json=payload, headers=HEADERS)
        if response.status_code == 429 and attempt <= retries:
            wait = 10 * (2 ** (attempt - 1))
            print(f"  Rate limited — waiting {wait}s before retry {attempt}/{retries}...")
            time.sleep(wait)
            continue
        response.raise_for_status()
        data = response.json()
        if "errors" in data:
            raise Exception(f"GraphQL error: {data['errors']}")
        return data["data"]


def query_with_delay(query: str, variables: dict = None, delay: float = 0.5) -> dict:
    """Small delay between API calls to stay within monday's rate limits."""
    time.sleep(delay)
    return run_query(query, variables)


# ── Data helpers ──────────────────────────────────────────────────────────────

def parse_date(date_str: str) -> str | None:
    """Convert MM/DD/YYYY (Smartsheet) to YYYY-MM-DD (monday API)."""
    if not date_str or not date_str.strip():
        return None
    try:
        return datetime.strptime(date_str.strip(), "%m/%d/%Y").strftime("%Y-%m-%d")
    except ValueError:
        print(f"  Warning: could not parse date '{date_str}'")
        return None


def normalize_engagement_status(raw: str) -> str:
    normalized = ENGAGEMENT_STATUS_MAP.get(raw.strip().lower())
    if not normalized:
        print(f"  Warning: unrecognized engagement status '{raw}', defaulting to 'Not Started'")
        return "Not Started"
    return normalized


def normalize_deliverable_status(raw: str) -> str:
    normalized = DELIVERABLE_STATUS_MAP.get(raw.strip().lower())
    if not normalized:
        print(f"  Warning: unrecognized deliverable status '{raw}', defaulting to 'To Do'")
        return "To Do"
    return normalized


def load_csv(path: str) -> list[dict]:
    """Loads the source CSV as-is. File is never modified."""
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def deduplicate_engagements(rows: list[dict]) -> list[dict]:
    """
    Extracts one engagement record per unique engagement_id.

    The source CSV repeats all engagement-level columns on every deliverable row.
    This deduplication is the core structural transformation — collapsing the
    flat file into the dimension table.

    engagement_start and engagement_end are engagement-level fields captured here.
    They will only appear on the Engagements board. Deliverables carry their own
    due_date, which is item-specific and distinct from these lifecycle dates.
    """
    seen = {}
    for row in rows:
        eid = row["engagement_id"]
        if eid not in seen:
            raw_status = row["engagement_status"].strip()
            seen[eid] = {
                "engagement_id":            eid,
                "engagement_name":          row["engagement_name"].strip(),
                "client":                   row["client"].strip(),
                "engagement_lead":          row["engagement_lead"].strip(),
                "engagement_start":         row["engagement_start"].strip(),
                "engagement_end":           row["engagement_end"].strip(),
                "budget":                   row["budget"].strip(),
                "engagement_status_raw":        raw_status,
                "engagement_status_normalized": normalize_engagement_status(raw_status),
            }
    return list(seen.values())


# ── Board and column creation ─────────────────────────────────────────────────

def create_board(name: str) -> str:
    query = """
    mutation CreateBoard($name: String!) {
        create_board(
            board_name: $name
            board_kind: public
            empty: true
        ) {
            id
        }
    }
    """
    data = query_with_delay(query, {"name": name})
    board_id = data["create_board"]["id"]
    print(f"  ✓ Board created: '{name}' (id: {board_id})")
    return board_id


def create_column(board_id: str, title: str, col_type: str) -> str:
    query = """
    mutation CreateColumn(
        $boardId: ID!
        $title: String!
        $type: ColumnType!
    ) {
        create_column(
            board_id: $boardId
            title: $title
            column_type: $type
        ) {
            id
        }
    }
    """
    data = query_with_delay(query, {"boardId": board_id, "title": title, "type": col_type})
    col_id = data["create_column"]["id"]
    print(f"    + {title} ({col_type}) → {col_id}")
    return col_id


def setup_engagements_board() -> tuple[str, dict]:
    """
    Dimension board: Nexus - Engagements.
    start_date / end_date explicitly named as engagement lifecycle dates.
    """
    print("\n[Step 1/4] Creating Engagements board (dimension)...")
    board_id = create_board("Nexus - Engagements")
    cols = {
        "engagement_id": create_column(board_id, "Engagement ID",    "text"),
        "client":        create_column(board_id, "Client",            "text"),
        "lead":          create_column(board_id, "Engagement Lead",   "text"),
        "start_date":    create_column(board_id, "Engagement Start",  "date"),
        "end_date":      create_column(board_id, "Engagement End",    "date"),
        "budget":        create_column(board_id, "Budget",            "numbers"),
        "status":        create_column(board_id, "Engagement Status", "status"),
    }
    return board_id, cols


def setup_deliverables_board() -> tuple[str, dict]:
    """
    Fact board: Nexus - Deliverables.
    due_date here is deliverable-specific — not the same as engagement start/end.

    Note: the Connect Boards column (board_relation type) cannot be created via
    the API — it must be added manually in the monday.com UI after Phase 1 runs.
    Phase 2 will query the board to find it automatically by type.
    Reference: https://developer.monday.com/api-reference/reference/connect
    """
    print("\n[Step 2/4] Creating Deliverables board (fact)...")
    board_id = create_board("Nexus - Deliverables")
    cols = {
        "deliverable_id": create_column(board_id, "Deliverable ID",     "text"),
        "assignee":       create_column(board_id, "Assignee",           "text"),
        "due_date":       create_column(board_id, "Due Date",           "date"),
        "priority":       create_column(board_id, "Priority",           "status"),
        "status":         create_column(board_id, "Deliverable Status", "status"),
        "hours":          create_column(board_id, "Hours Estimated",    "numbers"),
        # "engagement" (board_relation) is added manually in the UI — see phase_1()
    }
    return board_id, cols


def get_board_relation_column(board_id: str) -> str:
    """
    Queries the Deliverables board and returns the ID of the board_relation column
    added manually in the monday.com UI. Fails clearly if none is found.
    """
    query = """
    query GetColumns($boardId: ID!) {
        boards(ids: [$boardId]) {
            columns {
                id
                type
                title
            }
        }
    }
    """
    data = query_with_delay(query, {"boardId": board_id})
    columns = data["boards"][0]["columns"]
    for col in columns:
        if col["type"] == "board_relation":
            print(f"  ✓ Found Connect Boards column: '{col['title']}' → {col['id']}")
            return col["id"]
    raise Exception(
        "No board_relation column found on the Deliverables board. "
        "Add a Connect Boards column in the monday.com UI and link it to "
        "'Nexus - Engagements', then re-run Phase 2."
    )


# ── Data loading ──────────────────────────────────────────────────────────────

def create_item(board_id: str, name: str, col_values: dict) -> str:
    """Creates a single item on a board with the given column values."""
    query = """
    mutation CreateItem(
        $boardId: ID!
        $name: String!
        $colValues: JSON!
    ) {
        create_item(
            board_id: $boardId
            item_name: $name
            column_values: $colValues
            create_labels_if_missing: true
        ) {
            id
        }
    }
    """
    data = query_with_delay(query, {
        "boardId":   board_id,
        "name":      name,
        "colValues": json.dumps(col_values),
    })
    return data["create_item"]["id"]


def load_engagements(board_id: str, cols: dict, engagements: list[dict]) -> dict:
    """
    Loads the dimension table.
    Returns engagement_id → monday item_id for use when linking deliverables.
    """
    print(f"\n[Step 3/4] Loading {len(engagements)} engagements...")
    item_id_map = {}

    for eng in engagements:
        col_values = {
            cols["engagement_id"]: eng["engagement_id"],
            cols["client"]:        eng["client"],
            cols["lead"]:          eng["engagement_lead"],
            cols["budget"]:        eng["budget"],
            cols["status"]:        {"label": eng["engagement_status_normalized"]},
        }

        start = parse_date(eng["engagement_start"])
        if start:
            col_values[cols["start_date"]] = {"date": start}

        end = parse_date(eng["engagement_end"])
        if end:
            col_values[cols["end_date"]] = {"date": end}

        item_id = create_item(board_id, eng["engagement_name"], col_values)
        item_id_map[eng["engagement_id"]] = item_id

        raw  = eng["engagement_status_raw"]
        norm = eng["engagement_status_normalized"]
        tag  = f"['{raw}' → '{norm}']" if raw != norm else f"['{norm}']"
        print(f"  ✓ {eng['engagement_name']} {tag} → item {item_id}")

    return item_id_map


def load_deliverables(board_id: str, cols: dict, rows: list[dict], eng_item_map: dict):
    """
    Loads the fact table.
    Links each deliverable to its parent engagement via connect_boards.
    """
    print(f"\n[Step 4/4] Loading {len(rows)} deliverables...")

    for row in rows:
        raw_status        = row["deliverable_status"].strip()
        normalized_status = normalize_deliverable_status(raw_status)

        col_values = {
            cols["deliverable_id"]: row["deliverable_id"],
            cols["assignee"]:       row["assignee"].strip(),
            cols["hours"]:          row["hours_estimated"],
            cols["priority"]:       {"label": row["priority"].strip()},
            cols["status"]:         {"label": normalized_status},
        }

        due = parse_date(row["due_date"])
        if due:
            col_values[cols["due_date"]] = {"date": due}

        eng_item_id = eng_item_map.get(row["engagement_id"])
        if eng_item_id:
            col_values[cols["engagement"]] = {"item_ids": [eng_item_id]}
        else:
            print(f"  Warning: no engagement found for {row['deliverable_id']} "
                  f"(engagement_id: {row['engagement_id']})")

        item_id = create_item(board_id, row["deliverable_name"].strip(), col_values)
        tag = f"['{raw_status}' → '{normalized_status}']" if raw_status != normalized_status else f"['{normalized_status}']"
        print(f"  ✓ {row['deliverable_name']} {tag} → item {item_id}")


# ── Main ──────────────────────────────────────────────────────────────────────

def phase_1():
    """
    Creates both boards and all columns, writes board_config.json, then exits.

    After this runs you must manually connect the two boards in the monday.com UI
    (open either board → Board Settings → Connect Boards) before running Phase 2.
    This is a monday.com API limitation — boards cannot be connected programmatically.
    Reference: https://developer.monday.com/api-reference/reference/connect
    """
    if os.path.exists(CONFIG_OUTPUT):
        print(f"\nError: {CONFIG_OUTPUT} already exists — Phase 1 has already run.")
        print("  Delete it manually if you want to create fresh boards, then re-run.")
        sys.exit(1)

    # Config is written incrementally after each board is created so that a
    # mid-run failure doesn't leave boards in monday with no record of their IDs.
    config = {"engagement_status_map": ENGAGEMENT_STATUS_MAP,
              "deliverable_status_map": DELIVERABLE_STATUS_MAP}

    def save_config():
        with open(CONFIG_OUTPUT, "w") as f:
            json.dump(config, f, indent=2)

    print("\n[Phase 1] Creating boards and columns...")
    eng_board_id, eng_cols = setup_engagements_board()
    config["engagements_board_id"] = eng_board_id
    config["engagements_columns"]  = eng_cols
    save_config()

    del_board_id, del_cols = setup_deliverables_board()
    config["deliverables_board_id"] = del_board_id
    config["deliverables_columns"]  = del_cols
    save_config()

    print("\n" + "=" * 60)
    print("  Phase 1 Complete — Action Required")
    print("=" * 60)
    print(f"  Board IDs saved to : {CONFIG_OUTPUT}")
    print()
    print("  Before running Phase 2, do the following in monday.com:")
    print("  1. Open 'Nexus - Deliverables'")
    print("  2. Add a Connect Boards column (+) and name it 'Engagement'")
    print("  3. Link it to 'Nexus - Engagements'")
    print("  (The API cannot create this column type — it must be done in the UI)")
    print()
    print("  Then run:  python migration.py --phase 2")
    print("=" * 60)


def phase_2():
    """
    Reads board_config.json written by Phase 1 and loads all data.
    Boards must be connected in the monday.com UI before this runs.
    """
    if not os.path.exists(CONFIG_OUTPUT):
        print(f"Error: {CONFIG_OUTPUT} not found. Run Phase 1 first.")
        sys.exit(1)

    with open(CONFIG_OUTPUT) as f:
        config = json.load(f)

    eng_board_id = config["engagements_board_id"]
    eng_cols     = config["engagements_columns"]
    del_board_id = config["deliverables_board_id"]
    del_cols     = config["deliverables_columns"]

    # Locate the Connect Boards column added manually in the monday UI and
    # persist its ID back to board_config.json so validate.py can use it.
    print("\n[Phase 2] Looking for Connect Boards column on Deliverables board...")
    del_cols["engagement"]           = get_board_relation_column(del_board_id)
    config["deliverables_columns"]   = del_cols
    with open(CONFIG_OUTPUT, "w") as f:
        json.dump(config, f, indent=2)

    rows        = load_csv(CSV_PATH)
    engagements = deduplicate_engagements(rows)
    print(f"\nSource: {len(rows)} deliverable rows → {len(engagements)} unique engagements")

    print(f"\n[Phase 2] Loading data into existing boards...")
    eng_item_map = load_engagements(eng_board_id, eng_cols, engagements)
    load_deliverables(del_board_id, del_cols, rows, eng_item_map)

    print("\n" + "=" * 60)
    print("  Migration Complete")
    print("=" * 60)
    print(f"  Engagements loaded : {len(engagements)}")
    print(f"  Deliverables loaded: {len(rows)}")
    print("=" * 60)


def main():
    if not API_TOKEN:
        print("Error: MONDAY_API_TOKEN is not set. Add it to a .env file.")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Nexus Smartsheet → monday.com migration")
    parser.add_argument(
        "--phase",
        type=int,
        choices=[1, 2],
        required=True,
        help="1 = create boards and columns, 2 = load data (boards must be connected first)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  Nexus Consulting Group — monday.com Migration")
    print("=" * 60)

    if args.phase == 1:
        phase_1()
    else:
        phase_2()


if __name__ == "__main__":
    main()
