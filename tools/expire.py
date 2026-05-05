"""
expire.py — nightly TTL daemon for the substrate.

Walks ``backpack/**/*.md``, finds every item whose lease has expired
(``created_at + ttl_seconds < now``), and demotes each one to
``hoard/YYYY/MM/DD/`` with ``aged_out_at`` stamped.

Pinned items (``freshness_class: pinned``) are *never* expired here —
pinning is the operator's explicit "keep this near me regardless." Items
with no ``ttl_seconds`` (e.g. evergreen-references) are also skipped, since
they have no lease to overrun.

Hoard is write-once per ADR 0002 and the manifesto, so this only ever moves
files *into* hoard/. Nothing is deleted; everything remains searchable
forever via ``read_hoard()``.

Usage:

    python tools/expire.py /path/to/operator-root              # apply
    python tools/expire.py /path/to/operator-root --dry-run    # preview only
    python tools/expire.py /path/to/operator-root --now ISO    # pin clock for tests
    python tools/expire.py /path/to/operator-root --verbose    # also print kept items

Exits 0 on success (whether or not any items were demoted). Exits 1 if at
least one demote raised an exception. Stdout lists every demote / kept
decision; stderr carries the summary line. Cron / weaver can grep stdout
for ``demote `` to count work done, or just rely on stderr for noise.

Wire into the existing weaver daemon by adding to ``tools/weaver.py``:

    schedule.every().day.at("23:55").do(
        lambda: subprocess.run([sys.executable, "tools/expire.py", str(root)])
    )
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make ``substrate`` importable when this script is run directly.
_THIS = Path(__file__).resolve().parent
if str(_THIS) not in sys.path:
    sys.path.insert(0, str(_THIS))

from substrate import (  # noqa: E402
    demote_to_hoard,
    is_expired,
    iter_backpack,
)


def parse_now(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as e:
        raise SystemExit(f"--now must be ISO-8601, got {value!r}: {e}")
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def run(operator_root: Path, *, now: datetime, dry_run: bool, verbose: bool) -> tuple[int, int, list[str]]:
    """Return (demoted_count, error_count, lines_for_log)."""
    if not operator_root.is_dir():
        raise SystemExit(f"operator root does not exist: {operator_root}")

    demoted = 0
    errors = 0
    log: list[str] = []

    for path, fm, _body in iter_backpack(operator_root):
        rel = str(path.relative_to(operator_root))

        if fm.get("freshness_class") == "pinned":
            if verbose:
                log.append(f"  keep   pinned        {rel}")
            continue

        if not is_expired(fm, now=now):
            if verbose:
                log.append(f"  keep   fresh         {rel}")
            continue

        if dry_run:
            log.append(f"  would  demote        {rel}")
            demoted += 1
            continue

        try:
            target = demote_to_hoard(operator_root, path, now=now)
            log.append(f"  demote {rel} -> {target.relative_to(operator_root)}")
            demoted += 1
        except Exception as exc:
            log.append(f"  ERROR  {type(exc).__name__} on {rel}: {exc}")
            errors += 1

    return demoted, errors, log


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("operator_root", help="path to the operator root")
    p.add_argument(
        "--now",
        default=None,
        help="pin the clock to ISO-8601 (UTC if no offset). Defaults to actual now.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would be demoted without writing anything.",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="also print items that were kept (pinned or fresh).",
    )
    args = p.parse_args(argv)

    operator_root = Path(args.operator_root).resolve()
    now = parse_now(args.now)

    demoted, errors, log = run(
        operator_root,
        now=now,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    for line in log:
        print(line)
    verb = "would demote" if args.dry_run else "demoted"
    suffix = " (dry-run)" if args.dry_run else ""
    print(f"summary: {verb} {demoted} item(s){suffix} from {operator_root}", file=sys.stderr)
    if errors:
        print(f"errors:  {errors}", file=sys.stderr)

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
