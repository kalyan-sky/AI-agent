#!/usr/bin/env python3
"""Structural validation for the n8n workflow JSON files under n8n/workflows/.

This does NOT execute the workflows (n8n itself can't run in this sandbox —
see n8n/README.md). It checks the things that would otherwise only surface
by importing into a live n8n instance:

- each file is valid JSON with the required top-level workflow keys
- every node has a unique, non-empty `name` and `id`
- every connection source/target references a node that actually exists
- `errorWorkflow` / `executeWorkflow` id references point at another
  workflow file that exists in this same directory
- webhook path uniqueness across workflows (two workflows can't both
  claim the same path when imported into one n8n instance)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / "n8n" / "workflows"
REQUIRED_TOP_LEVEL_KEYS = {"name", "nodes", "connections", "settings", "id"}


def fail(errors: list[str], msg: str) -> None:
    errors.append(msg)


def validate_file(path: Path, errors: list[str]) -> dict | None:
    try:
        text = path.read_text()
    except OSError as exc:
        fail(errors, f"{path.name}: could not read file: {exc}")
        return None

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        fail(errors, f"{path.name}: invalid JSON: {exc}")
        return None

    missing = REQUIRED_TOP_LEVEL_KEYS - data.keys()
    if missing:
        fail(errors, f"{path.name}: missing top-level key(s): {sorted(missing)}")

    nodes = data.get("nodes", [])
    if not isinstance(nodes, list) or not nodes:
        fail(errors, f"{path.name}: 'nodes' must be a non-empty list")
        return data

    node_names = [n.get("name") for n in nodes]
    node_ids = [n.get("id") for n in nodes]

    if len(set(node_names)) != len(node_names):
        fail(errors, f"{path.name}: duplicate node names found: {node_names}")
    if any(not name for name in node_names):
        fail(errors, f"{path.name}: node with empty/missing 'name'")
    if len(set(node_ids)) != len(node_ids):
        fail(errors, f"{path.name}: duplicate node ids found")
    if any(not nid for nid in node_ids):
        fail(errors, f"{path.name}: node with empty/missing 'id'")

    for node in nodes:
        for required_field in ("type", "typeVersion", "position", "parameters"):
            if required_field not in node:
                fail(
                    errors,
                    f"{path.name}: node '{node.get('name', '?')}' missing '{required_field}'",
                )

    node_name_set = set(node_names)
    connections = data.get("connections", {})
    if not isinstance(connections, dict):
        fail(errors, f"{path.name}: 'connections' must be an object")
    else:
        for source_name, outputs in connections.items():
            if source_name not in node_name_set:
                fail(
                    errors,
                    f"{path.name}: connection source '{source_name}' is not a known node",
                )
            main_branches = outputs.get("main", []) if isinstance(outputs, dict) else []
            for branch in main_branches:
                for edge in branch:
                    target_name = edge.get("node")
                    if target_name not in node_name_set:
                        fail(
                            errors,
                            f"{path.name}: connection target '{target_name}' "
                            f"(from '{source_name}') is not a known node",
                        )

    return data


def main() -> int:
    if not WORKFLOWS_DIR.is_dir():
        print(f"ERROR: workflows directory not found: {WORKFLOWS_DIR}")
        return 1

    files = sorted(WORKFLOWS_DIR.glob("*.json"))
    if not files:
        print(f"ERROR: no workflow JSON files found in {WORKFLOWS_DIR}")
        return 1

    errors: list[str] = []
    parsed_by_id: dict[str, tuple[Path, dict]] = {}
    webhook_paths: dict[str, str] = {}

    for path in files:
        data = validate_file(path, errors)
        if data is None:
            continue
        wf_id = data.get("id")
        if wf_id:
            if wf_id in parsed_by_id:
                other_path, _ = parsed_by_id[wf_id]
                fail(errors, f"{path.name}: duplicate workflow id {wf_id} (also in {other_path.name})")
            parsed_by_id[wf_id] = (path, data)

        for node in data.get("nodes", []):
            if node.get("type") == "n8n-nodes-base.webhook":
                webhook_path = node.get("parameters", {}).get("path")
                if webhook_path:
                    if webhook_path in webhook_paths and webhook_paths[webhook_path] != path.name:
                        fail(
                            errors,
                            f"{path.name}: webhook path '{webhook_path}' also used in "
                            f"{webhook_paths[webhook_path]}",
                        )
                    webhook_paths[webhook_path] = path.name

    known_ids = set(parsed_by_id.keys())
    for path, data in parsed_by_id.values():
        for node in data.get("nodes", []):
            if node.get("type") in ("n8n-nodes-base.executeWorkflow",):
                ref = node.get("parameters", {}).get("workflowId", {})
                ref_value = ref.get("value") if isinstance(ref, dict) else None
                if ref_value and not str(ref_value).startswith("={{") and ref_value not in known_ids:
                    fail(
                        errors,
                        f"{path.name}: node '{node.get('name')}' references unknown "
                        f"workflow id '{ref_value}'",
                    )
        error_wf = data.get("settings", {}).get("errorWorkflow")
        if error_wf and error_wf not in known_ids:
            fail(errors, f"{path.name}: settings.errorWorkflow references unknown workflow id '{error_wf}'")

    if errors:
        print(f"FAILED: {len(errors)} error(s) found across {len(files)} workflow file(s):\n")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(f"OK: {len(files)} workflow file(s) structurally valid, {len(known_ids)} workflow id(s) cross-checked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
