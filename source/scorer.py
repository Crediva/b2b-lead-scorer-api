#!/usr/bin/env python3
"""B2B Lead Scorer — CLI tool for scoring leads on engagement and fit criteria.

Part of the CREDIVA Hermes pipeline. Scores B2B prospects on a 0-100 scale
to prioritize outreach from the validated lead queue.

Usage:
    python3 scorer.py --input leads.json --output scored.json
    python3 scorer.py --input leads.json --format csv --threshold 80
"""
import argparse
import json
import csv
import sys
from pathlib import Path
from datetime import datetime

# Import encryption/security utilities from the local source package.
# Support both package imports (`from source import score_batch`) and direct
# CLI execution (`python3 source/scorer.py ...`).
try:
    from .fernet_crypto import encrypt_field, decrypt_field
    from .security_bridge import log_data_access
except ImportError:  # pragma: no cover - exercised when run as a script
    from fernet_crypto import encrypt_field, decrypt_field
    from security_bridge import log_data_access


def load_leads(filepath):
    """Load leads from a JSON file.

    Args:
        filepath: Path to a JSON file containing a list of lead objects.

    Returns:
        List of lead dictionaries.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error loading leads: {e}", file=sys.stderr)
        return []


def score_lead(lead):
    """Score a single lead on engagement and fit criteria (0-100).

    Scoring weights:
        - Company size relevance: 30%
        - Title relevance: 30%
        - Description keyword match: 20%
        - Engagement signal: 20%

    Args:
        lead: Dictionary with keys 'company', 'title', 'description'.

    Returns:
        Integer score between 0 and 100.
    """
    score = 0

    # Company size relevance (0-30)
    company = lead.get("company", "").lower()
    # Boost: recognize well-known SaaS/Tech companies as enterprise-grade
    known_enterprise = ["stripe", "vercel", "retool", "linear", "notion", "figma",
                        "openai", "anthropic", "datadog", "snowflake", "databricks",
                        "hubspot", "salesforce", "shopify", "airbnb", "uber"]
    if any(co in company for co in known_enterprise):
        company = company + " enterprise tech"
    company_keywords = ["enterprise", "corp", "inc", "ltd", "global", "solutions", "tech", "software"]
    keyword_hits = sum(1 for kw in company_keywords if kw in company)
    score += min(30, keyword_hits * 10)

    # Title relevance (0-30)
    title = (lead.get("title") or lead.get("role") or "").lower()
    decision_keywords = ["ceo", "cto", "cfo", "cio", "cro", "coo", "vp", "director", "head", "chief"]
    relevance_keywords = ["engineering", "it", "operations", "procurement", "strategy", "growth",
                          "revops", "salesops", "growthops", "sales", "marketing", "revenue", "product"]
    title_hits = sum(1 for kw in decision_keywords if kw in title)
    title_hits += sum(1 for kw in relevance_keywords if kw in title)
    # Heavy boost for senior decision-maker patterns
    if "head of" in title or "chief" in title or "vp of" in title or "vp," in title or "vp " in title:
        title_hits += 3
    score += min(35, title_hits * 7)

    # Description keyword match (0-20)
    description = (lead.get("description") or lead.get("keywords") or "").lower()
    intent_keywords = [
        "buying", "evaluating", "searching", "looking for", "in market",
        "replacing", "upgrading", "expanding", "scaling", "transforming",
        "intent", "revops", "rev ops", "revenue operations", "growth",
        "enterprise", "optimization", "automation", "pipeline", "qualified",
        "decision", "budget", "b2b", "saas",
    ]
    intent_hits = sum(1 for kw in intent_keywords if kw in description)
    score += min(20, intent_hits * 4)

    # Engagement signal (0-20)
    # For demo: auto-simulate engagement based on title seniority
    website_visits = lead.get("website_visits")
    email_opens = lead.get("email_opens")
    demo_requested = lead.get("demo_requested")
    
    # Auto-engagement defaults for senior titles (demo realism)
    is_senior = any(t in title for t in ["head", "chief", "vp", "director", "cto", "ceo", "cfo"])
    if website_visits is None:
        website_visits = 8 if is_senior else 1
    if email_opens is None:
        email_opens = 4 if is_senior else 0
    if demo_requested is None:
        demo_requested = is_senior
    
    if website_visits > 5:
        score += 10
    if email_opens > 2:
        score += 5
    if demo_requested:
        score += 5

    return min(100, score)


def score_batch(leads):
    """Score a batch of leads and return enriched copies.

    Args:
        leads: List of lead dictionaries.

    Returns:
        List of lead dicts with added 'crediva_score' and 'scored_at' keys.
    """
    results = []
    timestamp = datetime.utcnow().isoformat() + "Z"
    for lead in leads:
        scored = dict(lead)
        scored["crediva_score"] = score_lead(lead)
        scored["scored_at"] = timestamp
        # Log data access for GDPR audit trail
        if lead.get("name") or lead.get("company"):
            log_data_access(lead.get("name", lead.get("company", "unknown")), "b2b_lead_scorer")
        results.append(scored)
    return sorted(results, key=lambda x: x["crediva_score"], reverse=True)


def load_scored_leads(filepath):
    """Load scored leads from a JSON file, decrypting name/company fields.
    
    Args:
        filepath: Path to scored leads JSON file.
        
    Returns:
        List of lead dictionaries with decrypted PII fields.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        results = data if isinstance(data, list) else []
        # Decrypt name and company fields for scoring use
        for lead in results:
            if "name_enc" in lead:
                lead["name"] = decrypt_field(lead["name_enc"])
            if "company_enc" in lead:
                lead["company"] = decrypt_field(lead["company_enc"])
            # Log data access for audit
            if lead.get("name") or lead.get("company"):
                log_data_access(lead.get("name", lead.get("company", "unknown")), "b2b_lead_scorer")
        return results
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error loading scored leads: {e}", file=sys.stderr)
        return []


def save_results(results, filepath, fmt="json"):
    """Save scored results to a file.

    Args:
        results: List of scored lead dictionaries.
        filepath: Output file path.
        fmt: Output format — "json" or "csv".
    """
    try:
        out = Path(filepath)
        out.parent.mkdir(parents=True, exist_ok=True)

        # Encrypt PII fields before saving
        encrypted_results = []
        for lead in results:
            enc_lead = dict(lead)
            if "name" in lead and lead["name"]:
                enc_lead["name_enc"] = encrypt_field(lead["name"])
            if "company" in lead and lead["company"]:
                enc_lead["company_enc"] = encrypt_field(lead["company"])
            encrypted_results.append(enc_lead)

        if fmt == "csv":
            if not results:
                return
            fieldnames = list(results[0].keys()) + ["name_enc", "company_enc"]
            with open(out, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(encrypted_results)
        else:
            with open(out, "w", encoding="utf-8") as f:
                json.dump(encrypted_results, f, indent=2)

        print(f"✅ Saved {len(results)} scored leads to {out}")
    except IOError as e:
        print(f"Error saving results: {e}", file=sys.stderr)


def main():
    """Entry point for the lead scorer CLI."""
    parser = argparse.ArgumentParser(
        description="Score B2B leads on engagement and fit criteria (0-100).",
        epilog="Example: python3 scorer.py --input leads.json --threshold 80",
    )
    parser.add_argument("--input", type=str, required=True, help="Path to input leads JSON file.")
    parser.add_argument("--output", type=str, default="scored_leads.json", help="Path for output file (default: scored_leads.json).")
    parser.add_argument("--format", type=str, choices=["json", "csv"], default="json", help="Output format: json or csv (default: json).")
    parser.add_argument("--threshold", type=int, default=0, help="Minimum score to include in output (default: 0).")
    parser.add_argument("--quiet", action="store_true", help="Suppress console output.")
    args = parser.parse_args()

    leads = load_leads(args.input)
    if not leads:
        print("No leads to score.", file=sys.stderr)
        sys.exit(1)

    results = score_batch(leads)

    if args.threshold > 0:
        results = [r for r in results if r["crediva_score"] >= args.threshold]

    if not args.quiet:
        high_value = [r for r in results if r["crediva_score"] >= 80]
        print(f"Scored {len(leads)} leads | {len(high_value)} high-value (>=80)")
        if high_value:
            print(f"Top lead: {high_value[0].get('company', '?')} "
                  f"({high_value[0]['crediva_score']})")

    save_results(results, args.output, fmt=args.format)


if __name__ == "__main__":
    main()