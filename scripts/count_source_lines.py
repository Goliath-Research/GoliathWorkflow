#!/usr/bin/env python3
import os
import sys

# Paths to ignore
IGNORE_DIRS = {
    '.git', '.venv', 'venv', 'env', '.pytest_cache', '.hypothesis',
    '.cursor', '.vscode', 'build', 'dist', '__pycache__', 'node_modules', '.agents'
}

# Resolve workspace directory (parent of scripts directory)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.dirname(SCRIPT_DIR)

def is_ignored(path):
    parts = os.path.normpath(path).split(os.sep)
    return any(part in IGNORE_DIRS for part in parts)

def count_file_lines(filepath, file_type):
    total = 0
    blank = 0
    comment = 0
    
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error reading {filepath}: {e}", file=sys.stderr)
        return 0, 0, 0
        
    total = len(lines)
    in_block_comment = False
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            blank += 1
            continue
            
        if file_type == 'python':
            if stripped.startswith('#'):
                comment += 1
            elif stripped.startswith('"""') or stripped.startswith("'''"):
                comment += 1
                if (stripped.count('"""') % 2 != 0) or (stripped.count("'''") % 2 != 0):
                    in_block_comment = not in_block_comment
            elif in_block_comment:
                comment += 1
                if '"""' in stripped or "'''" in stripped:
                    in_block_comment = not in_block_comment
        elif file_type in ('mssql', 'pgsql', 'sqlite', 'sql_generic'):
            if stripped.startswith('--'):
                comment += 1
            elif stripped.startswith('/*'):
                comment += 1
                if '*/' not in stripped:
                    in_block_comment = True
            elif in_block_comment:
                comment += 1
                if '*/' in stripped:
                    in_block_comment = False
        elif file_type == 'script':
            if filepath.endswith('.bat') or filepath.endswith('.cmd'):
                if stripped.lower().startswith('rem') or stripped.startswith('::'):
                    comment += 1
            else:
                if stripped.startswith('#'):
                    comment += 1
                    
    return total, blank, comment

def main():
    stats = {
        'python': {'files': [], 'total_lines': 0, 'blank_lines': 0, 'comment_lines': 0},
        'mssql': {'files': [], 'total_lines': 0, 'blank_lines': 0, 'comment_lines': 0},
        'pgsql': {'files': [], 'total_lines': 0, 'blank_lines': 0, 'comment_lines': 0},
        'sqlite': {'files': [], 'total_lines': 0, 'blank_lines': 0, 'comment_lines': 0},
        'script': {'files': [], 'total_lines': 0, 'blank_lines': 0, 'comment_lines': 0}
    }
    
    # Specific file-by-file categorization for generic SQL files
    custom_sql_mapping = {
        os.path.normpath("packages/methylenricher/methyl_enricher/sql/network_discovery_schema.sql"): "sqlite",
        os.path.normpath("packages/methylmapper/sample_dmps.sql"): "mssql",
        os.path.normpath("packages/methylmapper/methyl_mapper/NormalCDF.sql"): "mssql",
        os.path.normpath("packages/methylmapper/methyl_mapper/NormalCDFInverse.sql"): "mssql",
        os.path.normpath("packages/methylmapper/methyl_mapper/NormalCDFInverseAbramowitz.sql"): "mssql",
        os.path.normpath("packages/methylmapper/methyl_mapper/params.sql"): "mssql",
        os.path.normpath("packages/methylmapper/methyl_mapper/Samples.sql"): "mssql",
        os.path.normpath("packages/methylmapper/methyl_mapper/sample_genes.sql"): "mssql",
        os.path.normpath("packages/methylmapper/methyl_mapper/spMapDMP2Genes.sql"): "mssql",
        os.path.normpath("workflow_engine/delphi/db-designer/TransferObjsFromBatches.sql"): "mssql",
        os.path.normpath("workflow_engine/sql/wf_action_dispatch_metadata.sql"): "mssql",
    }
    
    for root, dirs, files in os.walk(WORKSPACE_DIR):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        if is_ignored(root):
            continue
            
        for file in files:
            filepath = os.path.join(root, file)
            rel_path = os.path.relpath(filepath, WORKSPACE_DIR)
            ext = os.path.splitext(file)[1].lower()
            
            file_type = None
            if ext == '.py':
                file_type = 'python'
            elif ext == '.sql':
                norm_root = root.lower()
                rel_path_norm = os.path.normpath(rel_path)
                if rel_path_norm in custom_sql_mapping:
                    file_type = custom_sql_mapping[rel_path_norm]
                elif 'sql_mssql' in norm_root or 'mssql' in norm_root:
                    file_type = 'mssql'
                elif 'sql_pg' in norm_root or 'pgsql' in norm_root or 'postgres' in norm_root:
                    file_type = 'pgsql'
                else:
                    file_type = 'mssql'
            elif ext in ('.sh', '.ps1', '.bat', '.cmd'):
                file_type = 'script'
                
            if file_type:
                total, blank, comment = count_file_lines(filepath, file_type)
                stats[file_type]['files'].append({
                    'path': rel_path,
                    'total': total,
                    'blank': blank,
                    'comment': comment,
                    'code': total - blank - comment
                })
                stats[file_type]['total_lines'] += total
                stats[file_type]['blank_lines'] += blank
                stats[file_type]['comment_lines'] += comment

    # Print summary
    print("=== SOURCE LINE COUNT REPORT ===")
    print(f"{'Language/Type':<18} | {'Files':<6} | {'Total Lines':<11} | {'Blank Lines':<11} | {'Comment Lines':<13} | {'Code Lines':<10}")
    print("-" * 80)
    
    all_total_files = 0
    all_total_lines = 0
    all_blank_lines = 0
    all_comment_lines = 0
    all_code_lines = 0
    
    for lang in ['python', 'mssql', 'pgsql', 'sqlite', 'script']:
        data = stats[lang]
        num_files = len(data['files'])
        tot = data['total_lines']
        blk = data['blank_lines']
        cmt = data['comment_lines']
        code = tot - blk - cmt
        
        all_total_files += num_files
        all_total_lines += tot
        all_blank_lines += blk
        all_comment_lines += cmt
        all_code_lines += code
        
        print(f"{lang:<18} | {num_files:<6} | {tot:<11} | {blk:<11} | {cmt:<13} | {code:<10}")
        
    print("-" * 80)
    print(f"{'TOTAL':<18} | {all_total_files:<6} | {all_total_lines:<11} | {all_blank_lines:<11} | {all_comment_lines:<13} | {all_code_lines:<10}")
    print()

if __name__ == '__main__':
    main()
