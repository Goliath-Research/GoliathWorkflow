"""
Core enrichment analysis functionality for MethylEnricher.

Supports MethylMapper combined CSV (all-gene_name-combined.csv) with optional
filtering by disease columns and DMP/gene metrics to focus on important genes.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import pandas as pd


# Evidence level order (higher index = stricter when used as min)
EVIDENCE_LEVEL_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3}

# Default Enrichr libraries optimized for methylation studies
DEFAULT_LIBRARIES = [
    "KEGG_2021_Human",
    "Reactome_2022",
    "GO_Biological_Process_2023",
    "GO_Molecular_Function_2023",
    "GO_Cellular_Component_2023",
    "MSigDB_Hallmark_2020",
    "WikiPathway_2023_Human"
]

# Cancer-focused presets.
# Explicit `libraries` always takes precedence over presets.
LIBRARY_PRESETS = {
    "cancer-core": [
        *DEFAULT_LIBRARIES,
        "ChEA_2022",
        "ENCODE_and_ChEA_Consensus_TFs_from_ChIP-X",
        "TRRUST_Transcription_Factors_2019",
        "DisGeNET",
        "Jensen_DISEASES",
        "GWAS_Catalog_2019",
    ],
    "cancer-extended": [
        *DEFAULT_LIBRARIES,
        "ChEA_2022",
        "ENCODE_and_ChEA_Consensus_TFs_from_ChIP-X",
        "TRRUST_Transcription_Factors_2019",
        "DisGeNET",
        "Jensen_DISEASES",
        "GWAS_Catalog_2019",
        "DSigDB",
        "DrugBank",
        "LINCS_L1000_Chem_Pert_up",
        "LINCS_L1000_Chem_Pert_down",
        "miRTarBase_2017",
    ],
}

# Friendly aliases for CLI/config readability. Keys are normalized to lowercase.
_LIBRARY_ALIASES = {
    "chea 2022": "ChEA_2022",
    "encode tf chip-seq": "ENCODE_and_ChEA_Consensus_TFs_from_ChIP-X",
    "trrust": "TRRUST_Transcription_Factors_2019",
    "disgenet": "DisGeNET",
    "jensen diseases": "Jensen_DISEASES",
    "gwas catalog": "GWAS_Catalog_2019",
    "dsigdb": "DSigDB",
    "drugbank": "DrugBank",
    "lincs l1000": "LINCS_L1000_Chem_Pert_up",
    "mirtarbase": "miRTarBase_2017",
}


def _normalize_library_name(name: str) -> str:
    """Normalize a human-friendly library name to an Enrichr key when possible."""
    cleaned = str(name).strip()
    if not cleaned:
        return cleaned
    return _LIBRARY_ALIASES.get(cleaned.lower(), cleaned)


def resolve_enrichr_libraries(
    libraries: Optional[List[str]] = None,
    library_preset: Optional[str] = None
) -> List[str]:
    """
    Resolve final Enrichr libraries from explicit list and/or named preset.

    Precedence:
      1) explicit libraries (if provided),
      2) library preset,
      3) DEFAULT_LIBRARIES.
    """
    if libraries:
        source = libraries
    elif library_preset:
        if library_preset not in LIBRARY_PRESETS:
            valid = ", ".join(sorted(LIBRARY_PRESETS))
            raise ValueError(f"Unknown library_preset '{library_preset}'. Valid presets: {valid}")
        source = LIBRARY_PRESETS[library_preset]
    else:
        source = DEFAULT_LIBRARIES

    # Preserve order and remove duplicates after normalization.
    resolved: List[str] = []
    seen = set()
    for raw in source:
        normalized = _normalize_library_name(raw)
        if normalized and normalized not in seen:
            resolved.append(normalized)
            seen.add(normalized)
    return resolved


class EnrichmentAnalyzer:
    """
    Perform Over-Representation Analysis (ORA) on gene lists using Enrichr databases.
    
    This class provides a clean API for running enrichment analysis and handles
    all the details of querying Enrichr, processing results, and saving outputs.
    """
    
    def __init__(
        self,
        libraries: Optional[List[str]] = None,
        library_preset: Optional[str] = None,
        organism: str = "Human",
        cutoff: float = 0.05
    ):
        """
        Initialize the EnrichmentAnalyzer.
        
        Args:
            libraries: List of Enrichr library names (highest precedence)
            library_preset: Named preset when libraries are not provided
            organism: Organism name for Enrichr (default: "Human")
            cutoff: Adjusted p-value cutoff for filtering significant results
        """
        self.libraries = resolve_enrichr_libraries(
            libraries=libraries,
            library_preset=library_preset
        )
        self.organism = organism
        self.cutoff = cutoff
        self.results = {}
        
    def _apply_csv_filters(
        self,
        df: pd.DataFrame,
        *,
        disease_only: bool = False,
        disease_column: str = "disease_associated",
        disease_association_types: Optional[List[str]] = None,
        min_disease_evidence_level: Optional[str] = None,
        min_disease_publications: Optional[int] = None,
        min_disease_score: Optional[float] = None,
        min_dmp_count: Optional[int] = None,
        min_unique_dmps: Optional[int] = None,
        max_gene_q_value: Optional[float] = None,
        min_mean_effect_size: Optional[float] = None,
        min_gene_z: Optional[float] = None,
        min_gene_importance: Optional[float] = None,
        feature_types: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """Apply MethylMapper-style filters to a DataFrame. Only columns that exist are used."""
        out = df.copy()
        n_before = len(out)

        if disease_only and disease_column in out.columns:
            out = out[out[disease_column].astype(str).str.upper().isin(("TRUE", "1", "YES"))]
            print(f"[INFO] Filter disease_associated=True: {len(out)} genes (was {n_before})")
            n_before = len(out)

        if disease_association_types and "disease_association_type" in out.columns:
            allowed = {s.strip().lower() for s in disease_association_types}
            out = out[out["disease_association_type"].astype(str).str.strip().str.lower().isin(allowed)]
            print(f"[INFO] Filter disease_association_type in {allowed}: {len(out)} genes (was {n_before})")
            n_before = len(out)

        if min_disease_evidence_level is not None and "disease_evidence_level" in out.columns:
            min_level = EVIDENCE_LEVEL_ORDER.get(min_disease_evidence_level.lower(), 0)
            def _level_ok(val):
                if pd.isna(val): return False
                return EVIDENCE_LEVEL_ORDER.get(str(val).lower(), 0) >= min_level
            out = out[out["disease_evidence_level"].apply(_level_ok)]
            print(f"[INFO] Filter disease_evidence_level >= {min_disease_evidence_level}: {len(out)} genes (was {n_before})")
            n_before = len(out)

        if min_disease_publications is not None and "disease_publications" in out.columns:
            out = out[pd.to_numeric(out["disease_publications"], errors="coerce").fillna(0) >= min_disease_publications]
            print(f"[INFO] Filter disease_publications >= {min_disease_publications}: {len(out)} genes (was {n_before})")
            n_before = len(out)

        if min_disease_score is not None and "disease_score" in out.columns:
            out = out[pd.to_numeric(out["disease_score"], errors="coerce").fillna(0) >= min_disease_score]
            print(f"[INFO] Filter disease_score >= {min_disease_score}: {len(out)} genes (was {n_before})")
            n_before = len(out)

        if min_dmp_count is not None and "dmp_count" in out.columns:
            out = out[pd.to_numeric(out["dmp_count"], errors="coerce").fillna(0) >= min_dmp_count]
            print(f"[INFO] Filter dmp_count >= {min_dmp_count}: {len(out)} genes (was {n_before})")
            n_before = len(out)

        if min_unique_dmps is not None and "unique_dmps" in out.columns:
            out = out[pd.to_numeric(out["unique_dmps"], errors="coerce").fillna(0) >= min_unique_dmps]
            print(f"[INFO] Filter unique_dmps >= {min_unique_dmps}: {len(out)} genes (was {n_before})")
            n_before = len(out)

        if max_gene_q_value is not None and "gene_q_value" in out.columns:
            gene_q = pd.to_numeric(out["gene_q_value"], errors="coerce")
            finite_mask = gene_q.notna()
            if finite_mask.any():
                keep_mask = (~finite_mask) | (gene_q <= max_gene_q_value)
                out = out[keep_mask]
                print(f"[INFO] Filter gene_q_value <= {max_gene_q_value}: {len(out)} genes (was {n_before})")
                n_before = len(out)
            else:
                print("[INFO] Skip gene_q_value filter: no finite gene_q_value values available.")

        if min_mean_effect_size is not None:
            for col in ("mean_effect_size", "mean_weight", "total_weight"):
                if col in out.columns:
                    out = out[pd.to_numeric(out[col], errors="coerce").fillna(0) >= min_mean_effect_size]
                    print(f"[INFO] Filter {col} >= {min_mean_effect_size}: {len(out)} genes (was {n_before})")
                    n_before = len(out)
                    break

        if min_gene_z is not None and "gene_z" in out.columns:
            z = pd.to_numeric(out["gene_z"], errors="coerce")
            out = out[z.abs() >= min_gene_z]
            print(f"[INFO] Filter |gene_z| >= {min_gene_z}: {len(out)} genes (was {n_before})")
            n_before = len(out)

        if min_gene_importance is not None:
            for col in ("gene_importance", "total_importance", "total_weight"):
                if col in out.columns:
                    out = out[pd.to_numeric(out[col], errors="coerce").fillna(0) >= min_gene_importance]
                    print(f"[INFO] Filter {col} >= {min_gene_importance}: {len(out)} genes (was {n_before})")
                    n_before = len(out)
                    break

        if feature_types and "feature_type" in out.columns:
            allowed = {s.strip().lower() for s in feature_types}
            out = out[out["feature_type"].astype(str).str.strip().str.lower().isin(allowed)]
            print(f"[INFO] Filter feature_type in {allowed}: {len(out)} genes (was {n_before})")

        return out

    def load_gene_list(
        self,
        input_path: Union[str, Path],
        top_n: Optional[int] = None,
        gene_column: Optional[str] = None,
        disease_only: bool = False,
        disease_column: str = "disease_associated",
        disease_association_types: Optional[List[str]] = None,
        min_disease_evidence_level: Optional[str] = None,
        min_disease_publications: Optional[int] = None,
        min_disease_score: Optional[float] = None,
        min_dmp_count: Optional[int] = None,
        min_unique_dmps: Optional[int] = None,
        max_gene_q_value: Optional[float] = None,
        min_mean_effect_size: Optional[float] = None,
        min_gene_z: Optional[float] = None,
        min_gene_importance: Optional[float] = None,
        feature_types: Optional[List[str]] = None,
        sort_by: Optional[str] = None,
        sort_ascending: bool = False
    ) -> List[str]:
        """
        Load gene list from a text file or MethylMapper combined CSV.
        
        For CSV/TSV, optional filters (from MethylMapper output) can be applied:
        disease_associated, disease_association_type, disease_evidence_level,
        disease_publications, disease_score, dmp_count, unique_dmps, gene_q_value,
        mean_effect_size, gene_z, gene_importance, feature_type.
        """
        input_path = Path(input_path)
        
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        suffix = input_path.suffix.lower()
        if suffix in [".csv", ".tsv"]:
            sep = "," if suffix == ".csv" else "\t"
            df = pd.read_csv(input_path, sep=sep)

            _gene_candidates = ["gene_name", "gene_id", "gene_symbol", "gene", "symbol"]
            if gene_column is None:
                gene_column = next((c for c in _gene_candidates if c in df.columns), None)
            elif gene_column not in df.columns:
                # Config/CLI asked for a column that is missing (e.g. CSV is gene_id from mapper)
                _fallback = next((c for c in _gene_candidates if c in df.columns), None)
                if _fallback:
                    print(f"[WARN] Column '{gene_column}' not in CSV; using '{_fallback}'. Columns: {list(df.columns)}")
                    gene_column = _fallback
                else:
                    raise ValueError(
                        f"Gene column '{gene_column}' not found. "
                        f"Columns found: {list(df.columns)}"
                    )

            if gene_column is None:
                raise ValueError(
                    "Could not determine gene column. Provide --gene-column. "
                    f"Columns found: {list(df.columns)}"
                )

            df = self._apply_csv_filters(
                df,
                disease_only=disease_only,
                disease_column=disease_column,
                disease_association_types=disease_association_types,
                min_disease_evidence_level=min_disease_evidence_level,
                min_disease_publications=min_disease_publications,
                min_disease_score=min_disease_score,
                min_dmp_count=min_dmp_count,
                min_unique_dmps=min_unique_dmps,
                max_gene_q_value=max_gene_q_value,
                min_mean_effect_size=min_mean_effect_size,
                min_gene_z=min_gene_z,
                min_gene_importance=min_gene_importance,
                feature_types=feature_types,
            )

            if sort_by is None and "total_weight" in df.columns:
                sort_by = "total_weight"
                print("[INFO] Sorting genes by total_weight (auto)")
            if sort_by is None and "gene_importance" in df.columns:
                sort_by = "gene_importance"
                print("[INFO] Sorting genes by gene_importance (auto)")

            if sort_by:
                if sort_by in df.columns:
                    print(f"[INFO] Sorting genes by {sort_by} ({'asc' if sort_ascending else 'desc'})")
                    df = df.sort_values(by=sort_by, ascending=sort_ascending)
                else:
                    print(f"[WARN] sort_by '{sort_by}' not found; skipping sort")

            if len(df) == 0:
                raise ValueError(
                    "No genes left after filters. Try relaxing or removing filters "
                    "(e.g. omit --disease-only, or loosen disease_association_type / min_disease_score / etc.). "
                    "Or use --input with a plain gene list and no CSV filters."
                )

            genes_raw = df[gene_column].dropna().astype(str).tolist()
            genes = []
            seen = set()
            for gene in genes_raw:
                gene = gene.strip()
                if gene and gene not in seen:
                    genes.append(gene)
                    seen.add(gene)
        else:
            if sort_by:
                print("[WARN] sort_by is only supported for CSV/TSV inputs; ignoring")
            with open(input_path) as f:
                genes = [line.strip() for line in f if line.strip()]

            if top_n and len(genes) > top_n:
                genes = genes[:top_n]

        print(f"[INFO] Loaded {len(genes)} gene symbols from {input_path}")
        return genes

    def _gene_weight_from_row(self, row: pd.Series) -> float:
        """Compute a single gene weight from a CSV row (gene-level or first feature row)."""
        for col in ("gene_importance", "total_importance", "total_weight", "mean_effect_size", "mean_weight"):
            if col in row.index and pd.notna(row.get(col)):
                try:
                    return float(row[col])
                except (TypeError, ValueError):
                    pass
        return 1.0

    def load_gene_list_with_weights(
        self,
        input_path: Union[str, Path],
        top_n: Optional[int] = None,
        gene_column: Optional[str] = None,
        disease_only: bool = False,
        disease_column: str = "disease_associated",
        disease_association_types: Optional[List[str]] = None,
        min_disease_evidence_level: Optional[str] = None,
        min_disease_publications: Optional[int] = None,
        min_disease_score: Optional[float] = None,
        min_dmp_count: Optional[int] = None,
        min_unique_dmps: Optional[int] = None,
        max_gene_q_value: Optional[float] = None,
        min_mean_effect_size: Optional[float] = None,
        min_gene_z: Optional[float] = None,
        min_gene_importance: Optional[float] = None,
        feature_types: Optional[List[str]] = None,
        sort_by: Optional[str] = None,
        sort_ascending: bool = False,
    ) -> Tuple[List[str], Dict[str, float]]:
        """
        Load gene list and per-gene weights for weighted enrichment and module scoring.
        Returns (genes, weight_by_gene). Weights are from gene_importance/total_weight/mean_effect_size when available.
        """
        input_path = Path(input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        suffix = input_path.suffix.lower()
        if suffix not in [".csv", ".tsv"]:
            genes = self.load_gene_list(
                input_path, top_n=top_n, gene_column=gene_column,
                disease_only=disease_only, disease_column=disease_column,
                disease_association_types=disease_association_types,
                min_disease_evidence_level=min_disease_evidence_level,
                min_disease_publications=min_disease_publications,
                min_disease_score=min_disease_score,
                min_dmp_count=min_dmp_count,
                min_unique_dmps=min_unique_dmps,
                max_gene_q_value=max_gene_q_value,
                min_mean_effect_size=min_mean_effect_size,
                min_gene_z=min_gene_z,
                min_gene_importance=min_gene_importance,
                feature_types=feature_types,
                sort_by=sort_by,
                sort_ascending=sort_ascending,
            )
            return genes, {g: 1.0 for g in genes}
        sep = "," if suffix == ".csv" else "\t"
        df = pd.read_csv(input_path, sep=sep)
        _gene_candidates = ["gene_name", "gene_id", "gene_symbol", "gene", "symbol"]
        gc = gene_column
        if gc is None:
            gc = next((c for c in _gene_candidates if c in df.columns), None)
        elif gc not in df.columns:
            gc = next((c for c in _gene_candidates if c in df.columns), None)
        if gc is None:
            raise ValueError("Could not determine gene column. Provide gene_column.")
        df = self._apply_csv_filters(
            df,
            disease_only=disease_only,
            disease_column=disease_column,
            disease_association_types=disease_association_types,
            min_disease_evidence_level=min_disease_evidence_level,
            min_disease_publications=min_disease_publications,
            min_disease_score=min_disease_score,
            min_dmp_count=min_dmp_count,
            min_unique_dmps=min_unique_dmps,
            max_gene_q_value=max_gene_q_value,
            min_mean_effect_size=min_mean_effect_size,
            min_gene_z=min_gene_z,
            min_gene_importance=min_gene_importance,
            feature_types=feature_types,
        )
        if len(df) == 0:
            raise ValueError(
                "No genes left after filters. Try relaxing filters (e.g. --min-disease-score, "
                "--min-disease-evidence-level, --disease-only) or use an input generated with "
                "disease enrichment (Grok/Open Targets) if you need disease-associated genes."
            )
        if sort_by is None and "total_weight" in df.columns:
            sort_by = "total_weight"
        if sort_by is None and "gene_importance" in df.columns:
            sort_by = "gene_importance"
        if sort_by and sort_by in df.columns:
            df = df.sort_values(by=sort_by, ascending=sort_ascending)
        # One row per gene: take first occurrence (already sorted) for weight
        weight_by_gene: Dict[str, float] = {}
        genes_ordered: List[str] = []
        seen = set()
        for _, row in df.iterrows():
            g = str(row[gc]).strip() if pd.notna(row[gc]) else ""
            if not g or g in seen:
                continue
            seen.add(g)
            genes_ordered.append(g)
            weight_by_gene[g] = self._gene_weight_from_row(row)
        if top_n and len(genes_ordered) > top_n:
            genes_ordered = genes_ordered[:top_n]
            weight_by_gene = {g: weight_by_gene[g] for g in genes_ordered}
        print(f"[INFO] Loaded {len(genes_ordered)} gene symbols with weights from {input_path}")
        return genes_ordered, weight_by_gene

    def run_enrichment(
        self,
        genes: List[str],
        output_dir: Union[str, Path]
    ) -> pd.DataFrame:
        """
        Run enrichment analysis for all libraries.
        
        Args:
            genes: List of gene symbols
            output_dir: Directory to save results
            
        Returns:
            Merged DataFrame with all enrichment results
        """
        # Lazy import to allow installation without gseapy
        try:
            import gseapy as gp
        except ImportError as ex:
            raise ImportError(
                "gseapy is required for enrichment analysis. "
                "Install with: pip install gseapy"
            ) from ex
        
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"[INFO] Running enrichment analysis on {len(genes)} genes")
        print(f"[INFO] Libraries: {', '.join(self.libraries)}")
        
        all_results = []
        
        for lib in self.libraries:
            print(f"\n[INFO] Querying {lib}...")
            
            try:
                enr = gp.enrichr(
                    gene_list=genes,
                    gene_sets=[lib],
                    outdir=str(output_dir),
                    cutoff=1.0,  # Store all results; filter later
                    background=None,  # Use Enrichr default
                    organism=(self.organism or "Human").strip().lower()
                )
                
                if hasattr(enr, "results") and enr.results is not None and not enr.results.empty:
                    df = enr.results.copy()
                    df["library"] = lib
                    all_results.append(df)
                    
                    # Save per-library results
                    per_lib_csv = output_dir / f"enrich_{lib}.csv"
                    df.to_csv(per_lib_csv, index=False)
                    print(f"[INFO] ✓ {lib}: {len(df)} terms found")
                    
                    # Show top hit if any significant
                    sig_df = df[df["Adjusted P-value"] <= self.cutoff]
                    if not sig_df.empty:
                        top_term = sig_df.iloc[0]
                        print(f"      Top hit: {top_term['Term']} (q={top_term['Adjusted P-value']:.2e})")
                else:
                    print(f"[WARN] No results returned for {lib}")
                    
            except Exception as e:
                print(f"[ERROR] Failed to process {lib}: {e}")
                continue
        
        if not all_results:
            print("\n[WARN] No enrichment results found across any library")
            return pd.DataFrame()
        
        # Merge and sort results
        merged = pd.concat(all_results, ignore_index=True)
        merged.sort_values(
            ["Adjusted P-value", "P-value", "Odds Ratio"],
            ascending=[True, True, False],
            inplace=True
        )
        
        # Save merged results
        merged_csv = output_dir / "enrichment_merged.csv"
        merged.to_csv(merged_csv, index=False)
        print(f"\n[INFO] ✓ Merged results saved: {merged_csv}")
        
        # Save top significant hits
        top_hits = merged[merged["Adjusted P-value"] <= self.cutoff].copy()
        if not top_hits.empty:
            top_hits = top_hits.head(200)
            top_csv = output_dir / f"enrichment_top_q{self.cutoff}.csv"
            top_hits.to_csv(top_csv, index=False)
            print(f"[INFO] ✓ Top significant hits: {top_csv} ({len(top_hits)} terms)")
        else:
            print(f"[WARN] No significant terms found at q ≤ {self.cutoff}")
        
        # Store results
        self.results = {
            "merged": merged,
            "significant": top_hits
        }
        
        # Print summary
        self._print_summary(merged, top_hits)
        
        return merged
    
    def _print_summary(self, merged: pd.DataFrame, top_hits: pd.DataFrame):
        """Print a summary of enrichment results."""
        print("\n" + "=" * 70)
        print("ENRICHMENT ANALYSIS SUMMARY")
        print("=" * 70)
        print(f"Total terms tested: {len(merged):,}")
        print(f"Significant terms (q ≤ {self.cutoff}): {len(top_hits):,}")
        
        if not top_hits.empty:
            print(f"\nLibraries with significant hits:")
            lib_counts = top_hits.groupby("library").size().sort_values(ascending=False)
            for lib, count in lib_counts.items():
                print(f"  • {lib}: {count} terms")
            
            print(f"\nTop 5 most significant terms:")
            for i, row in top_hits.head(5).iterrows():
                print(f"  {i+1}. {row['Term']}")
                print(f"     Library: {row['library']}, q-value: {row['Adjusted P-value']:.2e}")
                print(f"     Overlap: {row['Overlap']}, Odds Ratio: {row['Odds Ratio']:.2f}")
        
        print("=" * 70)


def run_enrichment(
    input_file: Union[str, Path],
    output_dir: Union[str, Path],
    libraries: Optional[List[str]] = None,
    library_preset: Optional[str] = None,
    top_n: Optional[int] = 200,
    cutoff: float = 0.05,
    organism: str = "Human",
    gene_column: Optional[str] = None,
    disease_only: bool = False,
    disease_association_types: Optional[List[str]] = None,
    min_disease_evidence_level: Optional[str] = None,
    min_disease_publications: Optional[int] = None,
    min_disease_score: Optional[float] = None,
    min_dmp_count: Optional[int] = None,
    min_unique_dmps: Optional[int] = None,
    max_gene_q_value: Optional[float] = None,
    min_mean_effect_size: Optional[float] = None,
    min_gene_z: Optional[float] = None,
    min_gene_importance: Optional[float] = None,
    feature_types: Optional[List[str]] = None,
    sort_by: Optional[str] = None,
    sort_ascending: bool = False
) -> pd.DataFrame:
    """
    Convenience function to run enrichment analysis in one call.
    Accepts MethylMapper combined CSV and optional filters to focus on important genes.
    """
    analyzer = EnrichmentAnalyzer(
        libraries=libraries,
        library_preset=library_preset,
        organism=organism,
        cutoff=cutoff
    )
    
    genes = analyzer.load_gene_list(
        input_file,
        top_n=top_n,
        gene_column=gene_column,
        disease_only=disease_only,
        disease_association_types=disease_association_types,
        min_disease_evidence_level=min_disease_evidence_level,
        min_disease_publications=min_disease_publications,
        min_disease_score=min_disease_score,
        min_dmp_count=min_dmp_count,
        min_unique_dmps=min_unique_dmps,
        max_gene_q_value=max_gene_q_value,
        min_mean_effect_size=min_mean_effect_size,
        min_gene_z=min_gene_z,
        min_gene_importance=min_gene_importance,
        feature_types=feature_types,
        sort_by=sort_by,
        sort_ascending=sort_ascending
    )
    results = analyzer.run_enrichment(genes, output_dir)
    
    return results

