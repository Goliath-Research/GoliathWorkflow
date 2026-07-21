"""Offline plant gene↔trait association enricher (Open Targets replacement for plants).

Open Targets / DisGeNET are human therapeutic databases and must not be called for
plant AGI / crop locus IDs. Operators supply a TSV/CSV of gene–trait rows (from
Gramene, SoyBase, MaizeGDB, literature, etc.); this module joins them onto mapper
gene tables using the same ``disease_*`` column names as GeneDiseaseEnricher so
downstream enricher / module prior code keeps working.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional, Union

import pandas as pd

logger = logging.getLogger(__name__)

# Columns accepted in the operator-supplied table (aliases in parentheses).
_GENE_COLS = ("gene", "gene_name", "gene_id", "locus", "agi")
_TERM_COLS = ("disease_term", "trait_term", "trait", "phenotype")
_SCORE_COLS = ("score", "association_score", "weight")
_EVIDENCE_COLS = ("evidence_level", "evidence")
_PUB_COLS = ("publications", "nof_pmids", "pmid_count")
_DESC_COLS = ("description", "note", "annotation")


def _pick_column(df: pd.DataFrame, candidates: tuple[str, ...]) -> Optional[str]:
    lower_map = {str(c).strip().lower(): c for c in df.columns}
    for name in candidates:
        if name in lower_map:
            return lower_map[name]
    return None


class PlantTraitEnricher:
    """Join an offline gene↔trait table onto a gene DataFrame."""

    def __init__(
        self,
        plant_traits_path: Union[str, Path],
        disease_term: Optional[str] = None,
    ) -> None:
        self.plant_traits_path = Path(plant_traits_path).expanduser()
        self.disease_term = (disease_term or "").strip() or None
        self.grok_batch_size = 16  # used by Phase-3 batching in BedtoolsMapper
        self._table = self._load_table(self.plant_traits_path)
        self._by_gene = self._index_by_gene(self._table, self.disease_term)
        logger.info(
            "PlantTraitEnricher: loaded %d association rows (%d genes) from %s",
            len(self._table),
            len(self._by_gene),
            self.plant_traits_path,
        )

    @staticmethod
    def _load_table(path: Path) -> pd.DataFrame:
        if not path.is_file():
            raise FileNotFoundError(f"plant_traits_path not found: {path}")
        sep = "\t" if path.suffix.lower() in {".tsv", ".txt"} else ","
        df = pd.read_csv(path, sep=sep, dtype=str)
        if df.empty:
            logger.warning("Plant traits table is empty: %s", path)
        return df

    @classmethod
    def _index_by_gene(
        cls,
        df: pd.DataFrame,
        disease_term: Optional[str],
    ) -> Dict[str, Dict]:
        gene_col = _pick_column(df, _GENE_COLS)
        if gene_col is None:
            raise ValueError(
                "plant traits table must include a gene column "
                f"(one of {_GENE_COLS}); got columns={list(df.columns)}"
            )
        term_col = _pick_column(df, _TERM_COLS)
        score_col = _pick_column(df, _SCORE_COLS)
        evidence_col = _pick_column(df, _EVIDENCE_COLS)
        pub_col = _pick_column(df, _PUB_COLS)
        desc_col = _pick_column(df, _DESC_COLS)

        rows = df
        if disease_term and term_col is not None:
            needle = disease_term.lower()
            mask = rows[term_col].fillna("").astype(str).str.lower().str.contains(needle, regex=False)
            rows = rows.loc[mask]
            if rows.empty:
                logger.warning(
                    "No plant trait rows match disease_term=%r in column %s",
                    disease_term,
                    term_col,
                )

        by_gene: Dict[str, Dict] = {}
        for _, row in rows.iterrows():
            gene = str(row[gene_col]).strip()
            if not gene or gene.lower() == "nan":
                continue
            key = gene.upper()
            try:
                score = float(row[score_col]) if score_col and pd.notna(row[score_col]) else 1.0
            except (TypeError, ValueError):
                score = 1.0
            try:
                pubs = int(float(row[pub_col])) if pub_col and pd.notna(row[pub_col]) else 0
            except (TypeError, ValueError):
                pubs = 0
            evidence = (
                str(row[evidence_col]).strip().lower()
                if evidence_col and pd.notna(row[evidence_col])
                else ("high" if score >= 0.5 else "medium")
            )
            if evidence not in {"none", "low", "medium", "high"}:
                evidence = "medium"
            term = (
                str(row[term_col]).strip()
                if term_col and pd.notna(row[term_col])
                else (disease_term or "plant_trait")
            )
            desc = (
                str(row[desc_col]).strip()
                if desc_col and pd.notna(row[desc_col])
                else term
            )
            prev = by_gene.get(key)
            if prev is None or score >= float(prev.get("score", 0.0) or 0.0):
                by_gene[key] = {
                    "associated": True,
                    "association_type": "database",
                    "evidence_level": evidence,
                    "description": desc,
                    "publications": pubs,
                    "functional_role": term,
                    "score": score,
                    "source": "plant_traits",
                }
        return by_gene

    def enrich_gene_dataframe(
        self,
        df: pd.DataFrame,
        gene_column: str = "gene_name",
        disease_term: Optional[str] = None,
        separate_sources: bool = False,
    ) -> pd.DataFrame:
        del separate_sources  # single offline source
        if gene_column not in df.columns:
            raise ValueError(f"Column '{gene_column}' not found in DataFrame")

        # Optional per-call filter rebuild (same path / different term).
        index = self._by_gene
        term = (disease_term or self.disease_term or "").strip() or None
        if term and term != self.disease_term:
            index = self._index_by_gene(self._table, term)

        out = df.copy()
        keys = out[gene_column].astype(str).str.upper()

        def _get(key: str, field: str, default):
            if key in ("NAN", "NONE", ""):
                return default
            return index.get(key, {}).get(field, default)

        out["disease_associated_raw"] = keys.map(lambda k: bool(_get(k, "associated", False)))
        out["disease_associated"] = out["disease_associated_raw"]
        out["disease_association_type"] = keys.map(lambda k: _get(k, "association_type", "none"))
        out["disease_evidence_level"] = keys.map(lambda k: _get(k, "evidence_level", "none"))
        out["disease_description"] = keys.map(lambda k: _get(k, "description", None))
        out["disease_publications"] = keys.map(lambda k: int(_get(k, "publications", 0) or 0))
        out["disease_functional_role"] = keys.map(lambda k: _get(k, "functional_role", None))
        out["disease_source"] = keys.map(
            lambda k: _get(k, "source", "none") if k in index else "none"
        )
        out["disease_score"] = keys.map(lambda k: float(_get(k, "score", 0.0) or 0.0))
        out["gene_ncbi_link"] = ""
        out["gene_ensembl_link"] = ""
        out["gene_uniprot_link"] = ""

        n_hit = int(out["disease_associated"].sum())
        logger.info(
            "PlantTraitEnricher: %d/%d genes associated (source=plant_traits)",
            n_hit,
            len(out),
        )
        return out
