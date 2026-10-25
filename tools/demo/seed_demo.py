#!/usr/bin/env python3
"""Create a local demo operator account. Operator-run bootstrap, not a feature.

WHY THIS EXISTS
    The API has no registration endpoint (by design: no self-signup on an
    institutional system). A freshly migrated database therefore contains no
    users, so `POST /api/v1/auth/token` can only ever return 401. This script
    is the documented, explicit provisioning step.

SECURITY POSTURE
    * It writes only to the database named by DATABASE_URL.
    * It refuses to create a second account for an existing username.
    * It never prints the password back and never writes it to disk.
    * It is idempotent: re-running it leaves an existing user untouched.

USAGE
    export DATABASE_URL="sqlite:///./demo.db"
    export JWT_SECRET_KEY="<at least 32 characters>"
    python tools/demo/seed_demo.py --username demo --password 'demo-pass-123'
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select  # noqa: E402

from backend.app.core.security import get_password_hash  # noqa: E402
from backend.app.db.models import Institution, InstitutionMembership, User  # noqa: E402
from backend.app.db.session import SessionLocal  # noqa: E402

MIN_PASSWORD_LEN = 8


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision a local demo operator account.")
    parser.add_argument("--username", default="demo")
    parser.add_argument("--password", required=True, help="Demo password (min 8 chars).")
    parser.add_argument("--display-name", default="Demo Operator")
    parser.add_argument("--institution-code", default="INST-DEMO-001")
    parser.add_argument("--institution-name", default="Demo Institute of Technology")
    parser.add_argument("--role", default="institution_admin")
    args = parser.parse_args()

    if len(args.password) < MIN_PASSWORD_LEN:
        print(f"error: password must be at least {MIN_PASSWORD_LEN} characters", file=sys.stderr)
        return 2

    if not os.getenv("DATABASE_URL"):
        print(
            "warning: DATABASE_URL is not set; falling back to the backend default "
            "(sqlite:///./aicte_dev.db)",
            file=sys.stderr,
        )

    db = SessionLocal()
    try:
        institution = db.execute(
            select(Institution).where(Institution.institution_id == args.institution_code)
        ).scalar_one_or_none()
        if institution is None:
            institution = Institution(
                institution_id=args.institution_code,
                display_name=args.institution_name,
                status="active",
            )
            db.add(institution)
            db.commit()
            db.refresh(institution)
            print(f"created institution {institution.institution_id!r} (id={institution.id})")
        else:
            print(f"institution {institution.institution_id!r} already present (id={institution.id})")

        user = db.execute(select(User).where(User.username == args.username)).scalar_one_or_none()
        if user is not None:
            print(f"user {args.username!r} already exists (id={user.id}); left unchanged")
        else:
            user = User(
                username=args.username,
                hashed_password=get_password_hash(args.password),
                display_name=args.display_name,
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"created user {user.username!r} (id={user.id})")

        membership = db.execute(
            select(InstitutionMembership).where(
                InstitutionMembership.user_id == user.id,
                InstitutionMembership.institution_id == institution.id,
            )
        ).scalar_one_or_none()
        if membership is None:
            membership = InstitutionMembership(
                user_id=user.id,
                institution_id=institution.id,
                role=args.role,
                is_active=True,
            )
            db.add(membership)
            db.commit()
            print(f"granted role {args.role!r} on {institution.institution_id!r}")
        else:
            print(f"membership already present (role={membership.role!r})")

        print("\nready: POST /api/v1/auth/token with the username/password you supplied.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
