"""
Core enrichment analysis functionality for MethylEnricher
"""

import os
from pathlib import Path
from typing import List, Optional, Union
import pandas as pd


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


class EnrichmentAnalyzer:
    """
    Perform Over-Representation Analysis (ORA) on gene lists using Enrichr databases.
    
    This class provides a clean API for running enrichment analysis and handles
    all the details of querying Enrichr, processing results, and saving outputs.
    """
    
    def __init__(
        self,
        libraries: Optional[List[str]] = None,
        organism: str = "Human",
        cutoff: float = 0.05
    ):
        """
        Initialize the EnrichmentAnalyzer.
        
        Args:
            libraries: List of Enrichr library names (default: DEFAULT_LIBRARIES)
            organism: Organism name for Enrichr (default: "Human")
            cutoff: Adjusted p-value cutoff for filtering significant results
        """
        self.libraries = libraries if libraries is not None else DEFAULT_LIBRARIES
        self.organism = organism
        self.cutoff = cutoff
        self.results = {}
        
    def load_gene_list(
        self,
        input_path: Union[str, Path],
        top_n: Optional[int] = None,
        gene_column: Optional[str] = None,
        disease_only: bool = False,
        disease_column: str = "disease_associated",
        sort_by: Optional[str] = None,
        sort_ascending: bool = False
    ) -> List[str]:
        """
        Load gene list from a text file.
        
        Args:
            input_path: Path to input file with one gene symbol per line
            top_n: If specified, return only the top N genes
            gene_column: Gene column to use when input is CSV/TSV
            disease_only: If True, filter to disease-associated genes (CSV only)
            disease_column: Column used for disease association filtering
            sort_by: Column to sort by when input is CSV/TSV
            sort_ascending: If True, sort ascending (default: descending)
            
        Returns:
            List of gene symbols
        """
        input_path = Path(input_path)
        
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        suffix = input_path.suffix.lower()
        if suffix in [".csv", ".tsv"]:
            sep = "," if suffix == ".csv" else "\t"
            df = pd.read_csv(input_path, sep=sep)

            if gene_column is None:
                candidate_cols = ["gene_name", "gene_symbol", "gene", "symbol", "gene_id"]
                gene_column = next((c for c in candidate_cols if c in df.columns), None)

            if gene_column is None or gene_column not in df.columns:
                raise ValueError(
                    "Could not determine gene column. Provide --gene-column. "
                    f"Columns found: {list(df.columns)}"
                )

            if disease_only:
                if disease_column in df.columns:
                    df = df[df[disease_column].astype(bool)]
                else:
                    print(f"[WARN] disease_only requested but '{disease_column}' not found; using all genes")

            if sort_by is None and "total_weight" in df.columns:
                sort_by = "total_weight"
                print("[INFO] Sorting genes by total_weight (auto)")

            if sort_by:
                if sort_by in df.columns:
                    print(f"[INFO] Sorting genes by {sort_by} ({'asc' if sort_ascending else 'desc'})")
                    df = df.sort_values(by=sort_by, ascending=sort_ascending)
                else:
                    print(f"[WARN] sort_by '{sort_by}' not found; skipping sort")

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
                    organism=self.organism
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
    top_n: Optional[int] = 200,
    cutoff: float = 0.05,
    organism: str = "Human",
    gene_column: Optional[str] = None,
    disease_only: bool = False,
    sort_by: Optional[str] = None,
    sort_ascending: bool = False
) -> pd.DataFrame:
    """
    Convenience function to run enrichment analysis in one call.
    
    Args:
        input_file: Path to gene list file
        output_dir: Directory to save results
        libraries: Enrichr libraries to query
        top_n: Use only top N genes from list
        cutoff: Adjusted p-value cutoff
        organism: Organism for Enrichr
        
    Returns:
        DataFrame with merged enrichment results
    """
    analyzer = EnrichmentAnalyzer(
        libraries=libraries,
        organism=organism,
        cutoff=cutoff
    )
    
    genes = analyzer.load_gene_list(
        input_file,
        top_n=top_n,
        gene_column=gene_column,
        disease_only=disease_only,
        sort_by=sort_by,
        sort_ascending=sort_ascending
    )
    results = analyzer.run_enrichment(genes, output_dir)
    
    return results

