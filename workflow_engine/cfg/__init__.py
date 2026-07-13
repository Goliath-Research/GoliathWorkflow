"""Configuration registry (cfg): DB-backed config with filesystem materialization."""

from .kinds import CFG_KINDS, Kind
from .store import ConfigStore, FileConfigStore, content_hash
from .materialize import materialize_store
from .import_fs import import_filesystem
from .storage_expand import expand_storage_endpoint, redact_credential
from .study_membership import (
    list_study_group_members,
    list_study_groups,
    materialize_study_membership,
    set_study_group,
    set_study_group_members,
)
from .sync_on_start import ensure_study_work_synced

__all__ = [
    "CFG_KINDS",
    "Kind",
    "ConfigStore",
    "FileConfigStore",
    "content_hash",
    "materialize_store",
    "import_filesystem",
    "expand_storage_endpoint",
    "redact_credential",
    "set_study_group",
    "set_study_group_members",
    "list_study_groups",
    "list_study_group_members",
    "materialize_study_membership",
    "ensure_study_work_synced",
]
