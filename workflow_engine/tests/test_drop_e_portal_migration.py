"""Guard e_portal → portal.UserRoles copy-before-drop.

RBAC.spGetUserNavTree joins portal.viewUserAllRoles. Replacing that view with
an empty portal.UserRoles and then DROP SCHEMA e_portal CASCADE deletes the
source rows. Upgrade scripts must copy first.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

SQL_PG = Path(__file__).resolve().parents[1] / "sql_pg"
MIGRATION = SQL_PG / "migrations" / "20260822_drop_e_portal.sql"
RBAC_PARITY = SQL_PG / "rbac_api_parity.sql"

_COPY = re.compile(
    r'INSERT\s+INTO\s+portal\."UserRoles".*FROM\s+e_portal\."UserRoles"',
    re.IGNORECASE | re.DOTALL,
)
_DROP = re.compile(r"DROP\s+SCHEMA\s+IF\s+EXISTS\s+e_portal\s+CASCADE", re.IGNORECASE)
_VIEW = re.compile(
    r'CREATE\s+OR\s+REPLACE\s+VIEW\s+portal\."viewUserAllRoles"',
    re.IGNORECASE,
)


class DropEPortalMigrationTests(unittest.TestCase):
    def test_migration_copies_user_roles_before_drop(self) -> None:
        text = MIGRATION.read_text(encoding="utf-8")
        copy = _COPY.search(text)
        drop = _DROP.search(text)
        view = _VIEW.search(text)
        self.assertIsNotNone(copy, f"{MIGRATION.name} must copy e_portal.UserRoles")
        self.assertIsNotNone(view, f"{MIGRATION.name} must define portal.viewUserAllRoles")
        self.assertIsNotNone(drop, f"{MIGRATION.name} must drop e_portal")
        self.assertLess(copy.start(), view.start())
        self.assertLess(copy.start(), drop.start())
        self.assertLess(view.start(), drop.start())

    def test_rbac_parity_copies_user_roles_before_view(self) -> None:
        text = RBAC_PARITY.read_text(encoding="utf-8")
        copy = _COPY.search(text)
        view = _VIEW.search(text)
        self.assertIsNotNone(copy, f"{RBAC_PARITY.name} must copy e_portal.UserRoles if present")
        self.assertIsNotNone(view, f"{RBAC_PARITY.name} must define portal.viewUserAllRoles")
        self.assertLess(copy.start(), view.start())
        self.assertIsNone(_DROP.search(text), "rbac_api_parity.sql must not drop e_portal")
