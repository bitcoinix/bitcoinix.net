"""Fails when security.txt expires soon, or too far ahead.

Usage: check-security-txt-expiry.py SECURITY_TXT

RFC 9116 recommends an Expires less than a year ahead. Expires must be
updated before it passes; this fails 30 days before.
"""

import sys
from datetime import datetime, timedelta, timezone

WARN_BEFORE = timedelta(days=30)
MAX_AHEAD = timedelta(days=366)


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    expires = [
        line.partition(":")[2].strip()
        for line in open(sys.argv[1], encoding="utf-8")
        if line.lower().startswith("expires:")
    ]
    if len(expires) != 1:
        sys.exit("security.txt: expected exactly one Expires")

    # fromisoformat() reads `Z` and fractional seconds since Python 3.11
    expiry = datetime.fromisoformat(expires[0])
    if expiry.tzinfo is None:
        sys.exit(f"security.txt: Expires {expires[0]} has no time zone")
    now = datetime.now(timezone.utc)

    if expiry <= now:
        sys.exit(f"security.txt: Expires {expires[0]} has passed. Set it to a date less than a year ahead.")
    if expiry - now < WARN_BEFORE:
        sys.exit(
            f"security.txt: Expires {expires[0]} is less than {WARN_BEFORE.days} days ahead. "
            f"Set it to a date less than a year ahead."
        )
    if expiry - now > MAX_AHEAD:
        sys.exit(f"security.txt: Expires {expires[0]} is more than a year ahead (RFC 9116, 2.5.5)")
    print(f"security.txt expires {expires[0]}, in {(expiry - now).days} days")


if __name__ == "__main__":
    main()
