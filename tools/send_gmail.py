"""Send a built newsletter issue through the Gmail API.

Recipients are given on demand for each issue; they are not stored in .env.

Usage:
    # Test send to yourself (GMAIL_SENDER) - the default
    .venv/bin/python tools/send_gmail.py .tmp/issues/<slug>/manifest.json

    # Send to this issue's recipients (comma-separated), after the test is approved
    .venv/bin/python tools/send_gmail.py <manifest> --to "a@example.com, b@example.com"

    # Build the message without sending; saves message.eml for inspection
    .venv/bin/python tools/send_gmail.py <manifest> --dry-run

Each recipient gets their own copy, so addresses are never exposed.
Infographics are attached inline (Content-ID), which Gmail displays reliably.
First run opens a browser to approve access; token.json is saved afterwards.
Gmail limits a personal account to roughly 500 recipients per day.
"""
import argparse
import base64
import html as htmllib
import json
import mimetypes
import os
import re
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

from _common import ROOT, fail

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
EMAIL_RE = re.compile(r"[^@\s,;<>]+@[^@\s,;<>]+\.[A-Za-z]{2,}")


def env_path(var, default):
    p = Path(os.getenv(var, default) or default)
    return p if p.is_absolute() else ROOT / p


def gmail_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    cred_file = env_path("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    token_file = env_path("GOOGLE_TOKEN_FILE", "token.json")
    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not cred_file.exists():
                fail(f"{cred_file.name} not found. Download the OAuth Desktop client JSON "
                     "from Google Cloud Console and save it in the project folder.")
            flow = InstalledAppFlow.from_client_secrets_file(str(cred_file), SCOPES)
            creds = flow.run_local_server(port=0)
        token_file.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def html_to_text(html):
    html = re.sub(r"(?is)<(style|title)[^>]*>.*?</\1>", "", html)
    html = re.sub(r'(?is)<div style="display:none.*?</div>', "", html)  # preheader
    html = re.sub(r'(?is)<img[^>]*alt="([^"]*)"[^>]*>', r"\n[Infographic: \1]\n", html)
    html = re.sub(r'(?is)<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>', r"\2 (\1)", html)
    html = re.sub(r"(?i)<li[^>]*>", "\n- ", html)
    html = re.sub(r"(?i)</(p|h1|h2|div|tr|ul)>", "\n", html)
    text = htmllib.unescape(re.sub(r"<[^>]+>", "", html))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return "\n".join(line.strip() for line in text.splitlines()).strip() + "\n"


def build_message(manifest, sender, sender_name, to):
    html = Path(manifest["html"]).read_text()
    msg = EmailMessage()
    msg["Subject"] = manifest["subject"]
    msg["From"] = formataddr((sender_name, sender)) if sender_name else sender
    msg["To"] = to
    msg.set_content(html_to_text(html))
    msg.add_alternative(html, subtype="html")
    html_part = msg.get_payload()[1]
    for img in manifest["images"]:
        path = Path(img["path"])
        ctype = mimetypes.guess_type(path.name)[0] or "image/png"
        maintype, subtype = ctype.split("/")
        html_part.add_related(path.read_bytes(), maintype=maintype, subtype=subtype,
                              cid=f"<{img['cid']}>", filename=path.name, disposition="inline")
    return msg


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("manifest", help="Path to the issue's manifest.json")
    p.add_argument("--to", help="Comma-separated recipients for this issue (default: test to GMAIL_SENDER)")
    p.add_argument("--dry-run", action="store_true", help="Build message.eml but do not send")
    args = p.parse_args()

    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text())
    sender = os.getenv("GMAIL_SENDER", "").strip()
    if not sender:
        fail("GMAIL_SENDER is empty in .env.")
    sender_name = os.getenv("GMAIL_SENDER_NAME", "").strip()

    if args.to:
        recipients = list(dict.fromkeys(r.strip() for r in args.to.split(",") if r.strip()))
        bad = [r for r in recipients if not EMAIL_RE.fullmatch(r)]
        if bad:
            fail(f"Not valid email address(es): {', '.join(bad)}")
        if not recipients:
            fail("--to has no addresses.")
    else:
        recipients = [sender]

    if args.dry_run:
        msg = build_message(manifest, sender, sender_name, recipients[0])
        out = manifest_path.parent / "message.eml"
        out.write_bytes(bytes(msg))
        print(f"Dry run: message for {len(recipients)} recipient(s) saved -> {out}")
        return

    service = gmail_service()
    sent, failed = [], []
    for to in recipients:
        msg = build_message(manifest, sender, sender_name, to)
        raw = base64.urlsafe_b64encode(bytes(msg)).decode()
        try:
            resp = service.users().messages().send(userId="me", body={"raw": raw}).execute()
            sent.append({"to": to, "id": resp.get("id")})
            print(f"Sent to {to}")
        except Exception as e:  # keep going so one bad address doesn't stop the run
            failed.append({"to": to, "error": str(e)[:300]})
            print(f"FAILED for {to}: {str(e)[:300]}")

    log = manifest_path.parent / "send_log.json"
    history = json.loads(log.read_text()) if log.exists() else []
    history.append({"at": datetime.now().isoformat(timespec="seconds"),
                    "mode": "send" if args.to else "test", "sent": sent, "failed": failed})
    log.write_text(json.dumps(history, indent=2))
    print(f"Done: {len(sent)} sent, {len(failed)} failed. Log -> {log}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
