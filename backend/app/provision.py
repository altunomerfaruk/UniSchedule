import argparse
import getpass
import json
import os
from pathlib import Path
import secrets

from sqlalchemy import select

from .auth import password_hash
from .database import Base, SessionLocal, engine
from .migrations import backfill_saved_snapshots, migrate_schema
from .models import AdminAccount
from .seed import seed_fall_data


def prepare_database() -> None:
    Base.metadata.create_all(bind=engine)
    migrate_schema(engine)
    with SessionLocal() as db:
        seed_fall_data(db)
        backfill_saved_snapshots(db)


def create_admin(username: str, password: str) -> None:
    username = username.strip().lower()
    if not 3 <= len(username) <= 80 or not username.replace("_", "").replace("-", "").isalnum():
        raise SystemExit("Username must be 3–80 letters, digits, underscores or hyphens.")
    if len(password) < 14:
        raise SystemExit("Admin password must contain at least 14 characters.")
    prepare_database()
    with SessionLocal() as db:
        if db.scalar(select(AdminAccount).where(AdminAccount.username == username)):
            raise SystemExit("This admin username already exists.")
        db.add(AdminAccount(username=username, password_hash=password_hash(password)))
        db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Provision a local UniSchedule administrator.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dev-admin", action="store_true", help="Generate a random local development admin account.")
    group.add_argument("--create-admin", metavar="USERNAME", help="Create an administrator with a prompted password.")
    args = parser.parse_args()
    if args.dev_admin:
        if os.getenv("UNISCHEDULE_ENV") == "production" or os.getenv("UNISCHEDULE_ENABLE_DEV_BOOTSTRAP") != "1":
            raise SystemExit("Development bootstrap requires UNISCHEDULE_ENABLE_DEV_BOOTSTRAP=1 outside production.")
        credentials = Path(os.getenv("UNISCHEDULE_DEV_CREDENTIALS_PATH", str(Path(__file__).resolve().parents[1] / ".dev-admin-credentials.json")))
        if credentials.exists():
            raise SystemExit(f"Existing credential file found: {credentials}")
        password = secrets.token_urlsafe(24)
        create_admin("admin", password)
        with credentials.open("x", encoding="utf-8") as handle:
            json.dump({"username": "admin", "password": password}, handle, indent=2)
            handle.write("\n")
        os.chmod(credentials, 0o600)
        print(f"Development administrator created. Credentials: {credentials}")
    else:
        password = getpass.getpass("Admin password: ")
        repeat = getpass.getpass("Repeat admin password: ")
        if password != repeat:
            raise SystemExit("Passwords do not match.")
        create_admin(args.create_admin, password)
        print("Administrator created.")


if __name__ == "__main__":
    main()
