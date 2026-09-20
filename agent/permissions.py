"""Central safety policy and audit trail for JARVIS tools."""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from pathlib import Path

APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / "JARVIS"
AUDIT_FILE = APP_DIR / "audit.log"

# Confirmation is enforced by ToolRegistry. This catalog makes the policy explicit
# and gives the UI/logs a stable severity independent of the model.
CRITICAL_TOOLS = {"shutdown", "delete", "kill", "email_send", "extract_archive", "jmeter_load_test", "loaderio_status", "edit_file", "run_command", "forget", "kg_forget"}
READ_ONLY_PREFIXES = ("inspect_", "find_", "project_", "android_", "cloudflare_", "manageengine_", "osint_", "kg_query", "kg_relate", "kg_show")

def severity(name: str, confirmed: bool = False) -> str:
    if name in CRITICAL_TOOLS:
        return "critical"
    if name.startswith(READ_ONLY_PREFIXES) or name in {"status","search","open_path","open_url","volume","clip_get","reminders","task_list","recall","calc","now","weather","web_search","screenshot","ps"}:
        return "safe"
    return "confirm" if not confirmed else "approved"

def audit(name: str, action: str, detail: str = "") -> None:
    try:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        detail = str(detail).replace("\n", " ")[:500]
        record = {"ts": datetime.now(timezone.utc).isoformat(), "tool": name, "action": action, "detail": detail}
        with AUDIT_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass
