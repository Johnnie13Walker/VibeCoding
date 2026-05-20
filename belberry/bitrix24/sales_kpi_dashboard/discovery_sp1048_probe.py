"""Read-only probe UF-полей SP «Встречи» (entityTypeId=1048)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
SALES_DASHBOARD_ROOT = PROJECT_ROOT.parent / "sales_dashboard"
if str(SALES_DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(SALES_DASHBOARD_ROOT))

from sales_dashboard.bitrix_client import BitrixClient  # noqa: E402


ENTITY_TYPE_ID = 1048


def main() -> int:
    client = BitrixClient()
    fields = (
        client.call("crm.item.fields", {"entityTypeId": ENTITY_TYPE_ID})
        .get("result", {})
        .get("fields", {})
    )
    print(render_fields(fields))
    return 0


def render_fields(fields: dict[str, dict[str, Any]]) -> str:
    lines = [
        "# SP 1048 «Встречи» — UF-поля (probe Phase 3)",
        "",
        "| Field ID | Title | Type | Required |",
        "|---|---|---|---|",
    ]
    for field_id, meta in sorted(fields.items()):
        if not field_id.startswith("ufCrm") and not field_id.startswith("UF_"):
            continue
        title = str(meta.get("title") or "").replace("|", "\\|")
        field_type = str(meta.get("type") or "")
        required = bool(meta.get("isRequired", False))
        lines.append(f"| `{field_id}` | {title} | {field_type} | {required} |")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
