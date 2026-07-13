"""Study group membership: portal.Samples → cfg enrollment → CSV materialization."""

from __future__ import annotations

import copy
import csv
import io
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .store import ConfigRecord, ConfigStore

ROLE_TO_ARM = {"control": "controls", "disease": "diseases"}


def resolve_processing_key(
    *,
    portal_sample_id: int,
    lab_sample_id: Optional[int] = None,
    processing_sample_key: Optional[str] = None,
    lab_sample_name: Optional[str] = None,
    participant_id: Optional[str] = None,
) -> str:
    """
    Resolve the filesystem / CSV sample id.

    Precedence: LabSamples.Sample → explicit key → Samples.ParticipantID.
    """
    for candidate in (lab_sample_name, processing_sample_key, participant_id):
        if candidate is not None and str(candidate).strip():
            return str(candidate).strip()
    raise ValueError(
        f"cannot resolve processing_sample_key for portalSampleId={portal_sample_id}"
        + (f" labSampleId={lab_sample_id}" if lab_sample_id is not None else "")
    )


def _groups_extra(rec: ConfigRecord) -> List[Dict[str, Any]]:
    groups = rec.extra.get("studyGroups")
    if isinstance(groups, list):
        return list(groups)
    return []


def _save_groups(store: ConfigStore, rec: ConfigRecord, groups: List[Dict[str, Any]]) -> ConfigRecord:
    return store.set_extra(rec.kind, rec.name, rec.version, studyGroups=groups)


def set_study_group(
    store: ConfigStore,
    study_name: str,
    *,
    role: str,
    label: str,
    list_filename: str,
    version: Optional[str] = None,
) -> Dict[str, Any]:
    if role not in ROLE_TO_ARM:
        raise ValueError("role must be 'control' or 'disease'")
    rec = store.get("study", study_name, version=version, include_secret=True)
    if rec is None:
        raise KeyError(f"study/{study_name} not found")
    groups = _groups_extra(rec)
    found = None
    for g in groups:
        if g.get("role") == role and g.get("label") == label:
            found = g
            break
    if found is None:
        found = {"role": role, "label": label, "listFilename": list_filename, "members": []}
        groups.append(found)
    else:
        found["listFilename"] = list_filename
        found.setdefault("members", [])
    _save_groups(store, rec, groups)
    return {
        "role": role,
        "label": label,
        "listFilename": list_filename,
        "memberCount": len(found.get("members") or []),
    }


def set_study_group_members(
    store: ConfigStore,
    study_name: str,
    *,
    role: str,
    label: str,
    members: Sequence[Dict[str, Any]],
    version: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Replace membership for one study group.

    Each member dict accepts:
      portalSampleId (required), labSampleId, processingSampleKey,
      labSampleName, participantId (for key resolution without DB).
    """
    if role not in ROLE_TO_ARM:
        raise ValueError("role must be 'control' or 'disease'")
    rec = store.get("study", study_name, version=version, include_secret=True)
    if rec is None:
        raise KeyError(f"study/{study_name} not found")
    groups = _groups_extra(rec)
    group = next((g for g in groups if g.get("role") == role and g.get("label") == label), None)
    if group is None:
        raise KeyError(f"study group {role}/{label} not found; call set-study-group first")

    resolved: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for raw in members:
        portal_id = int(raw["portalSampleId"])
        lab_id = raw.get("labSampleId")
        lab_id_int = int(lab_id) if lab_id is not None and str(lab_id) != "" else None
        key = resolve_processing_key(
            portal_sample_id=portal_id,
            lab_sample_id=lab_id_int,
            processing_sample_key=raw.get("processingSampleKey"),
            lab_sample_name=raw.get("labSampleName"),
            participant_id=raw.get("participantId"),
        )
        if key in seen:
            raise ValueError(f"duplicate processing_sample_key in group: {key}")
        seen.add(key)
        resolved.append(
            {
                "portalSampleId": portal_id,
                "labSampleId": lab_id_int,
                "processingSampleKey": key,
            }
        )
    group["members"] = resolved
    _save_groups(store, rec, groups)
    return resolved


def list_study_groups(
    store: ConfigStore, study_name: str, *, version: Optional[str] = None
) -> List[Dict[str, Any]]:
    rec = store.get("study", study_name, version=version)
    if rec is None:
        raise KeyError(f"study/{study_name} not found")
    out = []
    for g in _groups_extra(rec):
        out.append(
            {
                "role": g.get("role"),
                "label": g.get("label"),
                "listFilename": g.get("listFilename"),
                "memberCount": len(g.get("members") or []),
            }
        )
    return out


def list_study_group_members(
    store: ConfigStore,
    study_name: str,
    *,
    role: str,
    label: str,
    version: Optional[str] = None,
) -> List[Dict[str, Any]]:
    rec = store.get("study", study_name, version=version)
    if rec is None:
        raise KeyError(f"study/{study_name} not found")
    for g in _groups_extra(rec):
        if g.get("role") == role and g.get("label") == label:
            return list(g.get("members") or [])
    raise KeyError(f"study group {role}/{label} not found")


def sync_document_sample_paths(
    document: Dict[str, Any],
    groups: Sequence[Dict[str, Any]],
    *,
    data_dir: str,
) -> Dict[str, Any]:
    """Rewrite controls/diseases groups[].sample_paths from cfg membership."""
    doc = copy.deepcopy(document)
    hints = []
    by_arm: Dict[str, List[Dict[str, Any]]] = {"control": [], "disease": []}
    for g in groups:
        role = g.get("role")
        if role not in by_arm:
            continue
        filename = g.get("listFilename") or g.get("list_filename")
        if not filename:
            continue
        sample_path = f"{data_dir.rstrip('/')}/{filename}"
        by_arm[role].append(
            {
                "label": g.get("label"),
                "sample_paths": [sample_path],
            }
        )
        hints.append(
            {
                "role": role,
                "label": g.get("label"),
                "listFilename": filename,
                "samplePath": sample_path,
            }
        )

    for role, arm_key in ROLE_TO_ARM.items():
        arm_groups = by_arm[role]
        if not arm_groups:
            continue
        arm = doc.get(arm_key)
        if not isinstance(arm, dict):
            arm = {"label": role, "groups": []}
            doc[arm_key] = arm
        existing = {str(x.get("label")): x for x in (arm.get("groups") or []) if isinstance(x, dict)}
        merged = []
        for ng in arm_groups:
            label = str(ng["label"])
            prev = existing.get(label, {})
            row = dict(prev)
            row["label"] = label
            row["sample_paths"] = list(ng["sample_paths"])
            merged.append(row)
        # Preserve other groups that are not managed via cfg membership
        managed = {str(x["label"]) for x in arm_groups}
        for label, prev in existing.items():
            if label not in managed:
                merged.append(prev)
        arm["groups"] = merged

    doc["cfgStudyGroups"] = hints
    return doc


def write_group_csv(path: Path, sample_keys: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["sample"])
    for key in sorted(sample_keys):
        writer.writerow([key])
    path.write_text(buf.getvalue(), encoding="utf-8")


def materialize_study_membership(
    store: ConfigStore,
    work_root: Path | str,
    *,
    study_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    For published studies with ``extra.studyGroups``, write CSVs under
    ``/work/projects/<studyId>/data/`` and sync ``document_json`` sample_paths.
    """
    work_root = Path(work_root)
    written: List[str] = []
    studies = store.list("study", published_only=True)
    if study_name:
        studies = [s for s in studies if s.name == study_name]

    for rec in studies:
        groups = _groups_extra(rec)
        study_id = (
            rec.extra.get("studyId")
            or rec.document.get("study_id")
            or rec.document.get("studyId")
            or rec.name
        )
        data_dir = work_root / "projects" / str(study_id) / "data"
        data_dir_str = str(data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)

        if groups:
            for g in groups:
                filename = g.get("listFilename") or "samples.csv"
                keys = [
                    str(m["processingSampleKey"])
                    for m in (g.get("members") or [])
                    if m.get("processingSampleKey")
                ]
                csv_path = data_dir / filename
                write_group_csv(csv_path, keys)
                written.append(str(csv_path))

            synced = sync_document_sample_paths(rec.document, groups, data_dir=data_dir_str)
            store.upsert(
                "study",
                rec.name,
                synced,
                version=rec.version,
                status=rec.status,
                extra=rec.extra,
            )
            doc_to_write = synced
        else:
            doc_to_write = rec.document

        cfg_dir = work_root / "projects" / str(study_id) / "configs"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        out = cfg_dir / f"project_{rec.name}.json"
        out.write_text(
            __import__("json").dumps(doc_to_write, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        written.append(str(out))

    return {"written": written}


def study_data_dir(work_root: Path | str, study_id: str) -> Path:
    return Path(work_root) / "projects" / study_id / "data"
