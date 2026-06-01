#!/usr/bin/env python3
"""Cold mail batch sender for CREDIVA b2b_lead_scorer.

Reads prospects.csv, personalizes template, sends via Resend API.

Usage:
    python3 send_cold_mails.py --dry-run         # Preview only, no send
    python3 send_cold_mails.py --send --limit 5  # Send to first 5
    python3 send_cold_mails.py --send --all      # Send to all
"""
import csv
import os
import sys
import time
import json
import urllib.request
import argparse
from pathlib import Path
from datetime import datetime, timezone

# Configuration
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
FROM_EMAIL = "Alex from CREDIVA <hello@crediva.dev>"
REPLY_TO = "credivacompany@gmail.com"
DEMO_URL = "https://web-production-fd9a5.up.railway.app/"
PROSPECTS_CSV = Path("prospects.csv")
SENT_LOG = Path("data/sent_emails.json")

# Cold mail template (Version B — Pain + example)
SUBJECT_TEMPLATE = "Quick question for {company}"

BODY_TEMPLATE = """Hi {first_name},

Quick question — how much time does your team waste each week manually scoring leads at {company}?

Built an AI tool that does it in 30s. Stripe RevOps profile? 87/100 (A tier, "contact today"). Junior Dev at Retool? 20/100 (skip).

Try with your own data, no signup: {demo_url}

Worth 60 seconds?

Alex
CREDIVA"""

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:15px;line-height:1.6;color:#1a1a1a;max-width:600px">
<p>Hi {first_name},</p>

<p>Quick question — how much time does your team waste each week manually scoring leads at <strong>{company}</strong>?</p>

<p>Built an AI tool that does it in 30s. Stripe RevOps profile? 87/100 (A tier, "contact today"). Junior Dev at Retool? 20/100 (skip).</p>

<p>Try with your own data, no signup: <a href="{demo_url}" style="color:#4f46e5">{demo_url}</a></p>

<p>Worth 60 seconds?</p>

<p>Alex<br>
CREDIVA</p>
</body>
</html>"""


def load_prospects():
    """Load prospects from CSV."""
    prospects = []
    with open(PROSPECTS_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            prospects.append(row)
    return prospects


def load_sent():
    """Load already sent emails to avoid duplicates."""
    if not SENT_LOG.exists():
        return set()
    try:
        data = json.loads(SENT_LOG.read_text())
        return set(d['email'] for d in data)
    except:
        return set()


def save_sent(email, result):
    """Append to sent log."""
    SENT_LOG.parent.mkdir(exist_ok=True)
    data = []
    if SENT_LOG.exists():
        try:
            data = json.loads(SENT_LOG.read_text())
        except:
            data = []
    data.append({
        "email": email,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "result": result
    })
    SENT_LOG.write_text(json.dumps(data, indent=2))


def personalize(prospect):
    """Personalize template with prospect data."""
    return {
        "subject": SUBJECT_TEMPLATE.format(company=prospect['company']),
        "text": BODY_TEMPLATE.format(
            first_name=prospect['first_name'],
            company=prospect['company'],
            demo_url=DEMO_URL
        ),
        "html": HTML_TEMPLATE.format(
            first_name=prospect['first_name'],
            company=prospect['company'],
            demo_url=DEMO_URL
        )
    }


def send_email(to_email, subject, text, html):
    """Send email via Resend API."""
    payload = {
        "from": FROM_EMAIL,
        "to": [to_email],
        "subject": subject,
        "text": text,
        "html": html,
        "reply_to": REPLY_TO
    }
    
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        method="POST",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9"
        },
        data=json.dumps(payload).encode()
    )
    
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return {"status": "ok", "response": json.loads(resp.read().decode())}
    except urllib.error.HTTPError as e:
        return {"status": "error", "code": e.code, "message": e.read().decode()}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Preview without sending')
    parser.add_argument('--send', action='store_true', help='Actually send emails')
    parser.add_argument('--limit', type=int, default=None, help='Limit number of sends')
    parser.add_argument('--all', action='store_true', help='Send to all prospects')
    parser.add_argument('--delay', type=int, default=15, help='Seconds between sends (default 15)')
    args = parser.parse_args()
    
    if not args.dry_run and not args.send:
        print("ERROR: Specify --dry-run or --send")
        sys.exit(1)
    
    if args.send and not RESEND_API_KEY:
        print("ERROR: RESEND_API_KEY not set in environment")
        sys.exit(1)
    
    prospects = load_prospects()
    sent_emails = load_sent()
    
    # Filter out already-sent
    to_send = [p for p in prospects if p['email'] not in sent_emails]
    
    print(f"\n=== CREDIVA Cold Mail Sender ===")
    print(f"Total prospects in CSV: {len(prospects)}")
    print(f"Already sent: {len(sent_emails)}")
    print(f"Ready to send: {len(to_send)}")
    
    if args.limit:
        to_send = to_send[:args.limit]
        print(f"Limited to: {args.limit}")
    
    if not to_send:
        print("\nNothing to send. All prospects already contacted.")
        return
    
    print(f"\n=== {'DRY-RUN' if args.dry_run else 'SENDING'} {len(to_send)} EMAILS ===\n")
    
    success = 0
    failed = 0
    
    for i, prospect in enumerate(to_send, 1):
        email_data = personalize(prospect)
        
        print(f"\n--- [{i}/{len(to_send)}] {prospect['first_name']} {prospect['last_name']} ({prospect['email']}) ---")
        print(f"Company: {prospect['company']}")
        print(f"Subject: {email_data['subject']}")
        
        if args.dry_run:
            print(f"\n--- PREVIEW ---")
            print(email_data['text'])
            print(f"--- END PREVIEW ---")
        else:
            result = send_email(
                prospect['email'],
                email_data['subject'],
                email_data['text'],
                email_data['html']
            )
            
            if result['status'] == 'ok':
                print(f"✓ Sent! ID: {result['response'].get('id', 'unknown')}")
                save_sent(prospect['email'], result)
                success += 1
            else:
                print(f"✗ Failed: {result.get('message', 'unknown error')}")
                failed += 1
            
            # Delay between sends (anti-spam)
            if i < len(to_send):
                print(f"  Waiting {args.delay}s before next send...")
                time.sleep(args.delay)
    
    print(f"\n=== SUMMARY ===")
    if args.dry_run:
        print(f"DRY-RUN: {len(to_send)} emails previewed (NOT sent)")
    else:
        print(f"Sent: {success}")
        print(f"Failed: {failed}")
        print(f"Total in log: {len(load_sent())}")


if __name__ == '__main__':
    main()
