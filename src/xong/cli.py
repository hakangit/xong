from __future__ import annotations

import argparse
import sys

from xong.auth import generate_api_key, hash_api_key
from xong.db import get_session_factory
from xong.models import ApiKey


def cmd_create_key(args: argparse.Namespace) -> int:
    acts_for = [a.strip() for a in args.acts_for if a.strip()]
    if not acts_for:
        print("error: at least one --acts-for username required", file=sys.stderr)
        return 1

    raw = generate_api_key()
    key_hash = hash_api_key(raw)
    factory = get_session_factory()
    db = factory()
    try:
        row = ApiKey(key_hash=key_hash, agent_name=args.agent, acts_for=acts_for)
        db.add(row)
        db.commit()
        print(f"agent: {args.agent}")
        print(f"acts_for: {', '.join(acts_for)}")
        print(f"key: {raw}")
        print("(store the key now — it cannot be retrieved again)")
    finally:
        db.close()
    return 0


def cmd_link_identity(args: argparse.Namespace) -> int:
    from xong.models import User, UserIdentity

    factory = get_session_factory()
    db = factory()
    try:
        user = db.query(User).filter(User.username == args.user).one_or_none()
        if user is None:
            print(f"error: no user '{args.user}'", file=sys.stderr)
            return 1
        existing = (
            db.query(UserIdentity)
            .filter(UserIdentity.provider == args.provider, UserIdentity.subject == args.subject)
            .one_or_none()
        )
        if existing is not None:
            print(
                f"error: ({args.provider}, {args.subject}) already linked to user_id "
                f"{existing.user_id}; merge instead of relinking",
                file=sys.stderr,
            )
            return 1
        db.add(UserIdentity(provider=args.provider, subject=args.subject, user_id=user.id))
        db.commit()
        print(f"linked ({args.provider}, {args.subject}) -> {user.username} (id {user.id})")
    finally:
        db.close()
    return 0


def cmd_merge_users(args: argparse.Namespace) -> int:
    """Merge a duplicate row into the surviving one — moves every table with a
    users.id foreign key (enumerated from metadata, not hardcoded, so new
    tables can't be silently missed), then deletes the duplicate. One
    transaction: either the whole merge lands or none of it."""
    from sqlalchemy import text as sql

    from xong.db import Base
    from xong.models import User

    factory = get_session_factory()
    db = factory()
    try:
        keep = db.query(User).filter(User.username == args.into).one_or_none()
        drop = db.query(User).filter(User.username == args.from_user).one_or_none()
        if keep is None or drop is None:
            print("error: both users must exist", file=sys.stderr)
            return 1
        if keep.id == drop.id:
            print("error: same user", file=sys.stderr)
            return 1

        fk_cols = []
        for table in Base.metadata.sorted_tables:
            if table.name == "users":
                continue
            for column in table.columns:
                for fk in column.foreign_keys:
                    if fk.column.table.name == "users" and fk.column.name == "id":
                        fk_cols.append((table.name, column.name))

        # focus is unique per (user_id, date, task_id) and capped at 3/day by
        # the API; blind re-pointing can violate both, so drop the duplicate's
        # colliding rows first (the survivor's picks win).
        db.execute(
            sql(
                "DELETE FROM focus WHERE user_id = :drop AND (date, task_id) IN "
                "(SELECT date, task_id FROM focus WHERE user_id = :keep)"
            ),
            {"drop": drop.id, "keep": keep.id},
        )
        for table_name, column_name in fk_cols:
            db.execute(
                sql(f"UPDATE {table_name} SET {column_name} = :keep WHERE {column_name} = :drop"),
                {"keep": keep.id, "drop": drop.id},
            )
        # unique lower(email) index: free the address before the survivor
        # takes it — flush ordering would otherwise hit the constraint.
        moved_email = drop.email
        if moved_email and not keep.email:
            drop.email = None
            db.flush()
            keep.email = moved_email
        db.delete(drop)
        db.commit()
        moved = ", ".join(f"{t}.{c}" for t, c in fk_cols)
        print(f"merged '{args.from_user}' into '{args.into}' (re-pointed: {moved})")
    finally:
        db.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="xong", description="Xong admin CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create-key", help="Create an agent API key")
    p.add_argument("--agent", required=True, help="Agent name, e.g. agent")
    p.add_argument(
        "--acts-for",
        action="append",
        default=[],
        dest="acts_for",
        help="Username the agent may manage (repeatable)",
    )
    p.set_defaults(func=cmd_create_key)

    p = sub.add_parser("link-identity", help="Link an external identity to an existing user")
    p.add_argument("--user", required=True, help="Existing username to link to")
    p.add_argument("--provider", required=True, help='"oidc:<issuer>" or "proxy"')
    p.add_argument("--subject", required=True, help="OIDC sub, or the Remote-User value")
    p.set_defaults(func=cmd_link_identity)

    p = sub.add_parser("merge-users", help="Merge a duplicate user into the surviving one")
    p.add_argument("--into", required=True, help="Surviving username")
    p.add_argument("--from", required=True, dest="from_user", help="Duplicate username to absorb")
    p.set_defaults(func=cmd_merge_users)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
