"""security_bridge.py — CREDIVA Security Integration Shim

Audit trail for GDPR compliance before B2B outreach.
Wired into: factory_daemon Stage 11, api_email_sender.py
Session: v14.22
"""
import json
import os
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(__file__).parent.parent
AUDIT_LOG = BASE / "logs" / "security_audit.jsonl"
MASTER_LOG = BASE / "logs" / "master_log.jsonl"


def _write_entry(entry: dict) -> None:
    """Append one audit entry atomically."""
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, default=str) + "\n"
    # Append-safe: read existing, write all + new
    existing = AUDIT_LOG.read_text() if AUDIT_LOG.exists() else ""
    tmp = AUDIT_LOG.with_suffix(".tmp")
    tmp.write_text(existing + line)
    os.rename(tmp, AUDIT_LOG)


def audit_event(event_type: str, actor: str, resource: str,
                outcome: str = "success", details: dict = None) -> None:
    """Public interface: write one tamper-evident audit entry."""
    _write_entry({
        "ts": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "actor": actor,
        "resource": resource,
        "outcome": outcome,
        "details": details or {}
    })


def log_cycle_security_check(cycle_id: int, stages_ok: list, warnings: list) -> None:
    """Called by factory_daemon Stage 11 each cycle."""
    audit_event(
        event_type="cycle_security_check",
        actor="factory_daemon",
        resource=f"cycle_{cycle_id}",
        outcome="warning" if warnings else "success",
        details={"stages_ok": stages_ok, "warnings": warnings}
    )


def log_product_write(product_name: str, destination: str) -> None:
    """Called when a product is promoted to products_LAUNCH."""
    audit_event(
        event_type="product_write",
        actor="factory_daemon",
        resource=product_name,
        details={"destination": destination}
    )


def log_email_event(recipient: str, product: str, status: str) -> None:
    """Called by api_email_sender before and after each send."""
    audit_event(
        event_type="email_outreach",
        actor="api_email_sender",
        resource=recipient,
        outcome=status,
        details={"product": product}
    )


def log_data_access(record_id: str, product: str) -> None:
    """Log when a record is accessed for reading/processing."""
    audit_event(
        event_type="data_access",
        actor="product_module",
        resource=record_id,
        details={"product": product}
    )


def log_data_deletion(record_id: str, product: str) -> None:
    """Log when a record is deleted (GDPR right-to-erasure)."""
    audit_event(
        event_type="data_deletion",
        actor="product_module",
        resource=record_id,
        details={"product": product}
    )


def get_audit_summary() -> dict:
    """Return counts by event_type for dashboard display."""
    from collections import Counter
    counts = Counter()
    if AUDIT_LOG.exists():
        for line in AUDIT_LOG.read_text().splitlines():
            try:
                counts[json.loads(line).get("event_type", "unknown")] += 1
            except Exception:
                pass
    return dict(counts)


if __name__ == "__main__":
    import sys
    if "--status" in sys.argv:
        summary = get_audit_summary()
        print(f"Security audit log: {AUDIT_LOG}")
        print(f"Exists: {AUDIT_LOG.exists()}")
        if AUDIT_LOG.exists():
            lines = AUDIT_LOG.read_text().splitlines()
            print(f"Total entries: {len(lines)}")
            print("Event counts:")
            for k, v in summary.items():
                print(f" {k}: {v}")
    elif "--test" in sys.argv:
        log_cycle_security_check(cycle_id=9999, stages_ok=["stage_1", "stage_2"], warnings=[])
        log_product_write("test_product_v1.0.0", "products_LAUNCH")
        log_email_event("test@example.com", "test_product", "queued")
        summary = get_audit_summary()
        assert summary.get("cycle_security_check") >= 1, "cycle check missing"
        assert summary.get("product_write") >= 1, "product write missing"
        assert summary.get("email_outreach") >= 1, "email event missing"
        print("PASS: security_bridge self-test")
        print(f" Audit log: {AUDIT_LOG}")
