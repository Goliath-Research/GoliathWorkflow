import pandas as pd
import numpy as np
import json
import os
import math
from pathlib import Path
from typing import Dict, List, Any
import sys
import io

import importlib.resources
from . import models # Ensure models is importable in the package context


def find_data_start(lines: List[str]) -> int:
    """Find the line index where the data table starts (after header and comments)."""
    for i, line in enumerate(lines):
        if not line.startswith("#") and line.strip():
            return i
    return -1

def calculate_qscore_vectorized(rates: pd.Series) -> pd.Series:
    """Calculate Phred quality score from error rate using vectorized ops."""
    # Q = -10 * log10(Rate)
    
    q_scores = pd.Series(index=rates.index, dtype=float)
    valid_mask = rates > 0
    
    q_scores[valid_mask] = -10 * np.log10(rates[valid_mask])
    q_scores[~valid_mask] = 60 # Arbitrary high score for 0 error
    
    return q_scores.round().astype(int)

def parse_metrics_file(file_path: Path) -> Dict[str, Any]:
    """Parse a standard Picard metrics file (single row of metrics)."""
    with open(file_path, "r") as f:
        lines = f.readlines()
    
    data_start = find_data_start(lines)
    if data_start == -1:
        raise ValueError(f"No data found in {file_path}")
        
    # Read just 1 row of data
    df = pd.read_csv(file_path, sep="\t", skiprows=data_start, nrows=1)
    
    # Replace NaN with None
    df = df.replace({np.nan: None})
    
    # Convert to dict, keys as is (case sensitive)
    return df.iloc[0].to_dict()

def parse_table_file(file_path: Path, rename_cols: Dict[str, str] = None, **kwargs) -> Dict[str, List]:
    """Parse a Picard table file (multiple rows) using Pandas."""
    with open(file_path, "r") as f:
        lines = f.readlines()

    data_start = find_data_start(lines)
    if data_start == -1:
        raise ValueError(f"No data found in {file_path}")

    # Read CSV
    df = pd.read_csv(file_path, sep="\t", skiprows=data_start, **kwargs)
    
    if rename_cols:
        df = df.rename(columns=rename_cols)
    
    # Replace NaN with None for JSON compatibility
    df = df.replace({np.nan: None})
        
    # Return as Columnar Dict (Structure of Arrays)
    return df.to_dict(orient="list")

def parse_insert_size_file(file_path: Path):
    """Special handling for insert_size.txt which contains both metrics and histogram."""
    with open(file_path, "r") as f:
        content = f.read()

    # Split into metrics and histogram sections
    if "## HISTOGRAM" in content:
        metrics_part, hist_part = content.split("## HISTOGRAM")
    else:
        metrics_part = content
        hist_part = None

    # Parse metrics
    metrics_lines = [line for line in metrics_part.splitlines() if line.strip()]
    metrics_start = find_data_start(metrics_lines)
    
    # Use StringIO to read string as file for pandas
    metrics_df = pd.read_csv(io.StringIO("\n".join(metrics_lines[metrics_start:])), sep="\t", nrows=1)
    metrics = metrics_df.iloc[0].to_dict()

    # Parse histogram if present
    histogram = {}
    if hist_part:
        hist_lines = [line for line in hist_part.splitlines() if line.strip()]
        
        # Skip garbage header line (e.g., "java.lang.Integer")
        hist_start = 0
        for i, line in enumerate(hist_lines):
            if line.strip().startswith('insert_size'):
                hist_start = i
                break
        
        hist_df = pd.read_csv(io.StringIO("\n".join(hist_lines[hist_start:])), sep="\t")
        
        orientation = metrics.get('PAIR_ORIENTATION', 'FR')
        hist_df['pair_orientation'] = orientation
        
        # Replace NaN
        hist_df = hist_df.replace({np.nan: None})
        
        histogram = hist_df.to_dict(orient="list")

    return metrics, histogram

def build_alignment_qc_json(sample_id: str, qc_dir: Path) -> Dict:
    """Main function to parse all files and build the JSON structure using Pydantic models."""
    
    def get_path(filename):
        return qc_dir / filename

    # Quality Yield
    qy_metrics = parse_metrics_file(get_path("quality_yield.txt"))
    # Map keys to lowercase to match model fields
    qy_data = {k.lower(): v for k, v in qy_metrics.items()}
    quality_yield = models.QualityYield(**qy_data)

    # Mean Quality by Cycle
    mq_data = parse_table_file(
        get_path("mean_quality_by_cycle.txt"),
        rename_cols={"CYCLE": "cycle", "MEAN_QUALITY": "mean_quality"}
    )
    mean_quality_by_cycle = models.MeanQualityByCycle(**mq_data)

    # Quality Score Distribution
    qs_data = parse_table_file(
        get_path("qualityscore.txt"),
        rename_cols={"QUALITY": "Q"} 
    )
    # Map aliases manually since models.py uses aliases but parse_metrics returns dict with aliased keys
    # Actually, parse_table_file renames columns, so we match the field names or aliases?
    # models.py: quality_score: List[int] = Field(alias="Q")
    # If we renamed to "Q", we should pass "Q". 
    # WAIT: Pydantic by default expects field names, unless we use `populate_by_name=True` or pass by alias.
    # The model has `alias="Q"`. So passing `Q` is correct if we instantiate by alias.
    quality_score_distribution = models.QualityScoreDistribution.model_validate(qs_data)


    # Base Distribution by Cycle
    bd_data = parse_table_file(
        get_path("base_distribution_by_cycle.txt"),
        rename_cols={"CYCLE": "cycle"} # "PCT_A", etc are already in the file and match aliases
    )
    base_distribution_by_cycle = models.BaseDistributionByCycle.model_validate(bd_data)

    # GC Bias Summary
    gcb_summary = parse_metrics_file(get_path("gcbias_summary.txt"))
    # Map to model fields
    gc_bias_summary = models.GCBiasSummary(
        at_dropout=gcb_summary.get("AT_DROPOUT", 0.0),
        gc_dropout=gcb_summary.get("GC_DROPOUT", 0.0)
    )

    # GC Bias Details
    gc_details_data = parse_table_file(
        get_path("gcbias_detail.txt"),
        rename_cols={"ERROR_BAR_WIDTH": "ERROR_BAR"} # Match alias
    )
    gc_bias_details = models.GCBiasDetail.model_validate(gc_details_data)

    # Insert Size
    insert_metrics, insert_hist = parse_insert_size_file(get_path("insert_size.txt"))
    # Metrics
    im_data = {k.lower(): v for k, v in insert_metrics.items() if k != 'PAIR_ORIENTATION'}
    insert_size_metrics = models.InsertSizeMetrics(**im_data)
    
    # Histogram
    # insert_hist keys match aliases (e.g. "insert_size", "pair_orientation", "All_Reads.fr_count")
    insert_size_histogram = models.InsertSizeHistogram.model_validate(insert_hist)

    # Error Summary
    with open(get_path("sequencingArtifact.error_summary_metrics.txt"), "r") as f:
        lines = f.readlines()
    
    data_start = find_data_start(lines)
    df_error = pd.read_csv(get_path("sequencingArtifact.error_summary_metrics.txt"), sep="\t", skiprows=data_start)
    
    # Calculate QSCORE
    df_error['QSCORE'] = calculate_qscore_vectorized(df_error['SUBSTITUTION_RATE'])
    
    # We need to map columns to the aliases in ErrorSummary model
    # Aliases: REF, ALT, COUNT, RATE, QSCORE
    # File columns: REF_BASE, ALT_BASE, ALT_COUNT, SUBSTITUTION_RATE
    df_error = df_error.rename(columns={
        "REF_BASE": "REF",
        "ALT_BASE": "ALT",
        "ALT_COUNT": "COUNT",
        "SUBSTITUTION_RATE": "RATE"
    })
    
    df_error = df_error.replace({np.nan: None})
    
    # Prepare dict for validation
    error_data = df_error[["REF", "ALT", "COUNT", "RATE", "QSCORE"]].to_dict(orient="list")
    error_summaries = models.ErrorSummary.model_validate(error_data)

    # Pre-Adapter Summaries
    # Model ArtifactSummary aliases: ARTIFACT_NAME, TOTAL_QSCORE, WORST_CXT, WORST_CXT_QSCORE
    # File columns probably match these.
    pa_data = parse_table_file(
        get_path("sequencingArtifact.pre_adapter_summary_metrics.txt"),
        keep_default_na=False
    )
    pre_adapter_summaries = models.ArtifactSummary.model_validate(pa_data)
    
    # Bait Bias Summaries
    bb_data = parse_table_file(
        get_path("sequencingArtifact.bait_bias_summary_metrics.txt"),
        keep_default_na=False
    )
    bait_bias_summaries = models.ArtifactSummary.model_validate(bb_data)

    # Build Top Level Model
    alignment_qc = models.AlignmentQC(
        sample_id=sample_id,
        quality_yield=quality_yield,
        mean_quality_by_cycle=mean_quality_by_cycle,
        quality_score_distribution=quality_score_distribution,
        base_distribution_by_cycle=base_distribution_by_cycle,
        gc_bias_summary=gc_bias_summary,
        gc_bias_details=gc_bias_details,
        insert_size_metrics=insert_size_metrics,
        insert_size_histogram=insert_size_histogram,
        error_summaries=error_summaries,
        pre_adapter_summaries=pre_adapter_summaries,
        bait_bias_summaries=bait_bias_summaries
    )

    # Dump to JSON dict using aliases to match original output format
    return alignment_qc.model_dump(by_alias=True)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Parse Parabricks QC files to JSON")
    parser.add_argument("--metrics_root", default="metrics", help="Root directory containing sample QC folders")
    parser.add_argument("--schema", default=None, help="Path to schema.json. Defaults to bundled schema.")
    args = parser.parse_args()

    metrics_root = Path(args.metrics_root)
    if not metrics_root.exists():
        print(f"Metrics root {metrics_root} does not exist.")
        return

    # Find all *.qc-metrics directories
    qc_dirs = list(metrics_root.glob("*.qc-metrics"))
    
    if not qc_dirs:
        print("No .qc-metrics directories found.")
        return

    print(f"Found {len(qc_dirs)} sample directories.")


    for qc_dir in qc_dirs:
        sample_id = qc_dir.name.replace(".qc-metrics", "")
        output_file = metrics_root / f"{sample_id}.json"
        
        print(f"Processing {sample_id}...")
        try:
            qc_json = build_alignment_qc_json(sample_id, qc_dir)
            
            with open(output_file, "w") as out_f:
                json.dump(qc_json, out_f, indent=2)
            
            print(f"Validation (Pydantic) successful for sample {sample_id}")
            
        except Exception as e:
            print(f"Error processing {sample_id}: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()