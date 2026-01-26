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


import tarfile
import tempfile
import contextlib

@contextlib.contextmanager
def prepare_qc_input(input_path: Path):
    """
    Context manager that yields a Path to a .qc-metrics directory.
    If input_path is a directory, yields it directly.
    If input_path is a .tar archive, extracts it to a temp dir and yields the inner directory.
    """
    if input_path.is_dir():
        yield input_path
    elif input_path.is_file() and input_path.name.endswith('.tar'):
        with tempfile.TemporaryDirectory() as temp_dir:
            print(f"Extracting {input_path.name} to {temp_dir}...")
            with tarfile.open(input_path, "r") as tar:
                # Filter members to avoid extraction issues/path traversal if necessary, 
                # but for now standard extractall is fine for trusted internal tools.
                tar.extractall(path=temp_dir)
            
            # Find the extracted .qc-metrics directory
            temp_path = Path(temp_dir)
            extracted_dirs = list(temp_path.glob("*.qc-metrics"))
            
            # Sometimes tar structure might be top-level or nested. 
            # If explicit *.qc-metrics dir found, use it.
            if extracted_dirs:
                yield extracted_dirs[0]
            else:
                # Maybe the tar contents ARE the metrics files directly?
                # or nested differently. Let's assume standard parabricks structure for now.
                # If no specific *.qc-metrics dir, yielding temp_dir might be risky if files are scattered, 
                # but if the tar was 'folder.qc-metrics.tar', it usually contains 'folder.qc-metrics/'
                yield temp_path
    else:
        raise ValueError(f"Unsupported input type: {input_path}")

def parse_deduplication_metrics(file_path: Path):
    """Parse deduplication metrics file containing metrics class and histogram."""
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
    
    # Read CSV using pandas
    metrics_df = pd.read_csv(io.StringIO("\n".join(metrics_lines[metrics_start:])), sep="\t")
    metrics = metrics_df.replace({np.nan: None}).to_dict(orient="records")
    
    # Parse histogram if present
    histogram = {}
    if hist_part:
        hist_lines = [line for line in hist_part.splitlines() if line.strip()]
        # Header "java.lang.Double" is usually in the HISTOGRAM line we split on, 
        # so next line is BIN VALUE ...
        # But split removes "## HISTOGRAM", remaining might be "	java.lang.Double\nBIN..."
        
        # Find start of data header "BIN"
        hist_start = 0
        for i, line in enumerate(hist_lines):
            if line.strip().startswith('BIN'):
                hist_start = i
                break
        
        hist_df = pd.read_csv(io.StringIO("\n".join(hist_lines[hist_start:])), sep="\t")
        hist_df = hist_df.replace({np.nan: None})
        histogram = hist_df.to_dict(orient="list")

    return metrics, histogram

def parse_bam_log(file_path: Path) -> Dict[str, str]:
    """Parse the fq2bam log file for timing and version info."""
    log_data = {}
    with open(file_path, "r") as f:
        lines = f.readlines()
        
    # We look for the summary table at the end
    # [PB Info ...] ||        Program:                          Marking Duplicates, BQSR        ||
    
    for line in lines:
        if "||        Program:" in line:
            # Split by "Program:" explicitly
            log_data["program"] = line.split("Program:")[1].split("||")[0].strip()
        if "||        Version:" in line:
            log_data["version"] = line.split("Version:")[1].split("||")[0].strip()
        if "||        Start Time:" in line:
            log_data["start_time"] = line.split("Start Time:")[1].split("||")[0].strip()
        if "||        End Time:" in line:
            log_data["end_time"] = line.split("End Time:")[1].split("||")[0].strip()
        if "||        Total Time:" in line:
            log_data["total_time"] = line.split("Total Time:")[1].split("||")[0].strip()
            
    return log_data

def process_sample(sample_id: str, qc_input_path: Path, dedup_path: Path = None, log_path: Path = None) -> Dict:
    """Process a single sample given its component files."""
    
    # 1. Parse QC Metrics (AlignmentQC base)
    qc_dir_context = prepare_qc_input(qc_input_path)
    with qc_dir_context as qc_dir:
        # We need to construct the model but NOT return dict yet, because we want to add fields.
        # But build_alignment_qc_json returns a dict (dumped model).
        # We should modify build_alignment_qc_json to return the model OR instantiate it here?
        # Refactoring `build_alignment_qc_json` to return the model object would be cleaner,
        # but to minimize churn let's call it, get the dict, and re-instantiate or just add to dict 
        # (but we want validation).
        
        # STRATEGY: Update build_alignment_qc_json to accept optional extra args for the other metrics?
        # OR: Just run it, get the dict. Then parse extra files. Then make a new combined dict. 
        # Then validate the whole thing with AlignmentQC model.
        
        # Let's import the specific parser code into helper if needed, but `build_alignment_qc_json` 
        # does A LOT. Let's reuse it.
        base_json = build_alignment_qc_json(sample_id, qc_dir)
    
    # 2. Parse Deduplication
    if dedup_path and dedup_path.exists():
        dedup_metrics, dedup_hist = parse_deduplication_metrics(dedup_path)
        base_json["duplication_metrics"] = dedup_metrics
        base_json["duplication_histogram"] = dedup_hist
        
    # 3. Parse Log
    if log_path and log_path.exists():
        log_data = parse_bam_log(log_path)
        base_json["conversion_log"] = log_data
        
    # 4. Final Validation against complete model
    # This ensures everything matches models.AlignmentQC
    final_model = models.AlignmentQC.model_validate(base_json)
    return final_model.model_dump(by_alias=True)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Parse Parabricks QC files to JSON")
    parser.add_argument("--metrics_root", default="metrics", help="Root directory containing sample QC folders or tars")
    parser.add_argument("--schema", default=None, help="Path to schema.json. Defaults to bundled schema.")
    args = parser.parse_args()

    metrics_root = Path(args.metrics_root)
    if not metrics_root.exists():
        print(f"Metrics root {metrics_root} does not exist.")
        return

    # Discovery Strategy:
    # 1. Look for DIRECTORIES that match a sample pattern (checking if they contain the required files).
    # 2. Look for standalone .qc-metrics or .qc-metrics.tar files.
    
    # Let's iterate all subdirectories in metrics_root
    # If a subdir contains .qc-metrics.tar, it's a sample dir.
    # If a subdir IS name.qc-metrics, it's a legacy sample dir.
    
    processed_samples = set()
    
    # Case A: Sample Folders (e.g. sample_id/) containing sample_id.qc-metrics.tar
    # We iterate all dirs
    for item in metrics_root.iterdir():
        if item.is_dir():
            if item.name.endswith(".qc-metrics"): 
                # This is likely a direct QC dir (Legacy support)
                continue # We'll handle this in Case B cleanup or separate pass? 
                # actually let's just handle it.
            
            # Check for qc-metrics.tar inside
            tars = list(item.glob("*.qc-metrics.tar"))
            if tars:
                # Found a sample folder!
                qc_tar = tars[0]
                sample_id = item.name # Assume folder name is sample ID
                
                # Look for other files
                dedup = list(item.glob("*.deduplicate_metrics.txt"))
                dedup_file = dedup[0] if dedup else None
                
                log = list(item.glob("*.fq2bam_meth_LOG.log"))
                log_file = log[0] if log else None
                
                print(f"Processing Sample Folder: {sample_id}")
                try:
                    res = process_sample(sample_id, qc_tar, dedup_file, log_file)
                    out_path = item / f"{sample_id}.json"
                    with open(out_path, "w") as f:
                        json.dump(res, f, indent=2)
                    print(f"  -> Generated {out_path.name}")
                    processed_samples.add(sample_id)
                except Exception as e:
                    print(f"  Error processing {sample_id}: {e}", file=sys.stderr)
                    # traceback.print_exc()
                continue

    # Case B: Standalone files in root (Legacy / Simple mode)
    # qc-metrics dirs
    qc_dirs = list(metrics_root.glob("*.qc-metrics"))
    # qc-metrics tars (that weren't inside a processed folder? or in root?)
    qc_tars = list(metrics_root.glob("*.qc-metrics.tar"))
    
    all_inputs = qc_dirs + qc_tars
    
    for inp in all_inputs:
        # Determine ID
        if inp.name.endswith(".tar"):
            sid = inp.name.replace(".qc-metrics.tar", "")
        else:
            sid = inp.name.replace(".qc-metrics", "")
            
        if sid in processed_samples:
            continue
            
        # Check if parent is the sample dir (unlikely if we iterated root glob, unless root IS sample dir)
        # But "metrics_root" might contain "Sample1.qc-metrics.tar" directly.
        # Look for sibling dedup/log files in same dir
        dedup_path = inp.parent / f"{sid}.deduplicate_metrics.txt"
        log_path = inp.parent / f"{sid}.fq2bam_meth_LOG.log"
        
        # If they don't exist as specific names, maybe glob? 
        # For simplicity, strict naming for standalone files.
        d_p = dedup_path if dedup_path.exists() else None
        l_p = log_path if log_path.exists() else None
        
        print(f"Processing Standalone: {sid}")
        try:
            res = process_sample(sid, inp, d_p, l_p)
            out_path = inp.parent / f"{sid}.json"
            with open(out_path, "w") as f:
                json.dump(res, f, indent=2)
            print(f"  -> Generated {out_path.name}")
        except Exception as e:
            print(f"  Error processing {sid}: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()