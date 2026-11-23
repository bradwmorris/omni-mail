"""Fictional threads for reviewing the inbox without a Gmail account."""

from datetime import datetime, timedelta

ROWS = (
    ("studio", "Can you confirm Thursday at 10?", "Maya Chen", "maya@studio.example",
     "Hi Alex,\n\nCould you confirm whether Thursday at 10 works for the prototype review? I can hold that slot until tomorrow.\n\nThanks,\nMaya", "yes"),
    ("billing", "Payment failed for your workspace", "Northstar Billing", "billing@northstar.example",
     "We couldn't process this month's workspace payment. Please update your payment method before Friday to keep the workspace active.", "yes"),
    ("digest", "The Friday reading list", "Field Notes", "editor@fieldnotes.example",
     "This week: three essays on building tools for small teams, and a conversation about what makes a daily inbox worth keeping.", "no"),
    ("notes", "Notes from the research call", "Sam Rivera", "sam@research.example",
     "Thanks for the call. I've collected the notes for reference and will send the next draft when it's ready.", "no"),
    ("receipt", "Your November receipt", "Papertrail", "receipts@papertrail.example",
     "Your payment went through. This is a copy of your receipt for your records.", "no"),
    ("review", "Could you review the homepage copy?", "Nina Patel", "nina@studio.example",
     "Could you take a look at the homepage copy and send me your edits by Monday? I'll make the final pass after that.", "yes"),
    ("release", "November release notes", "Workbench Updates", "updates@workbench.example",
     "This release includes a new export option and a faster keyboard shortcut menu. Thanks for using Workbench.", "no"),
)


def sample_threads():
    threads = []
    first = datetime.fromisoformat("2026-11-22T09:15:00+11:00")
    for index, (key, subject, sender, address, body, decision) in enumerate(ROWS):
        timestamp = int((first - timedelta(hours=index * 5)).timestamp())
        message = {"id": key + "-latest", "from": f"{sender} <{address}>", "timestamp": timestamp,
                   "body": body}
        messages = [message]
        if key == "studio":
            messages.insert(0, {"id": key + "-earlier", "from": "Alex Reed <alex@example.invalid>",
                                "timestamp": timestamp - 86400,
                                "body": "Hi Maya,\n\nCould we find half an hour this week to look over the prototype together?\n\nAlex"})
        threads.append({"id": key, "subject": subject, "timestamp": timestamp, "sender": sender,
                        "preview": " ".join(body.split()), "target": message["id"],
                        "messages": messages, "sample_decision": decision})
    return threads
