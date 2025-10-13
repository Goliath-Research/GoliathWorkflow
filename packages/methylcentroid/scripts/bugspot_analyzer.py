#!/usr/bin/env python3
"""
Custom BugSpot analyzer for MethylCentroid project.
Detects common issues in scientific computing, GPU operations, and bioinformatics code.
"""

import ast
import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
import re

class MethylCentroidBugSpot:
    """Custom bug detector for MethylCentroid project."""
    
    def __init__(self):
        self.issues = []
        self.current_file = None
        
    def analyze_file(self, file_path: str) -> List[Dict[str, Any]]:
        """Analyze a single Python file for potential bugs."""
        self.current_file = file_path
        self.issues = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse the AST
            tree = ast.parse(content)
            
            # Run various analyzers
            self._check_division_by_zero(tree)
            self._check_array_operations(tree)
            self._check_gpu_memory_management(tree)
            self._check_file_operations(tree)
            self._check_numpy_operations(tree)
            self._check_hdf5_operations(tree)
            self._check_memory_leaks(tree)
            self._check_error_handling(tree)
            
        except SyntaxError as e:
            self.issues.append({
                "type": "syntax_error",
                "severity": "high",
                "message": f"Syntax error: {e}",
                "file": file_path,
                "line": e.lineno,
                "suggestion": "Fix the syntax error before proceeding"
            })
        except Exception as e:
            self.issues.append({
                "type": "analysis_error",
                "severity": "medium",
                "message": f"Error analyzing file: {e}",
                "file": file_path,
                "line": 1,
                "suggestion": "Check file encoding and content"
            })
        
        return self.issues
    
    def _check_division_by_zero(self, tree: ast.AST):
        """Check for potential division by zero."""
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Div, ast.FloorDiv)):
                if isinstance(node.right, ast.Constant) and node.right.value == 0:
                    self.issues.append({
                        "type": "division_by_zero",
                        "severity": "high",
                        "message": "Potential division by zero",
                        "file": self.current_file,
                        "line": node.lineno,
                        "suggestion": "Add a check to ensure the denominator is not zero"
                    })
    
    def _check_array_operations(self, tree: ast.AST):
        """Check for potential array index out of bounds."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Subscript):
                if isinstance(node.slice, ast.Index):
                    # Check for hardcoded large indices
                    if isinstance(node.slice.value, ast.Constant):
                        if isinstance(node.slice.value.value, int) and node.slice.value.value > 1000:
                            self.issues.append({
                                "type": "large_array_index",
                                "severity": "medium",
                                "message": "Large hardcoded array index",
                                "file": self.current_file,
                                "line": node.lineno,
                                "suggestion": "Verify array bounds or use dynamic indexing"
                            })
    
    def _check_gpu_memory_management(self, tree: ast.AST):
        """Check for GPU memory management issues."""
        gpu_imports = set()
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in ['cupy', 'cudf', 'cuml']:
                        gpu_imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module in ['cupy', 'cudf', 'cuml']:
                    gpu_imports.add(node.module)
        
        if gpu_imports:
            # Check for proper GPU memory cleanup
            has_memory_cleanup = False
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if hasattr(node.func, 'attr') and node.func.attr in ['free', 'clear_cache']:
                        has_memory_cleanup = True
                        break
            
            if not has_memory_cleanup:
                self.issues.append({
                    "type": "gpu_memory_management",
                    "severity": "medium",
                    "message": "GPU libraries imported but no explicit memory cleanup found",
                    "file": self.current_file,
                    "line": 1,
                    "suggestion": "Consider adding explicit GPU memory cleanup or using context managers"
                })
    
    def _check_file_operations(self, tree: ast.AST):
        """Check for file operation issues."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if hasattr(node.func, 'id') and node.func.id == 'open':
                    # Check if file is properly closed
                    if not self._has_proper_file_handling(node):
                        self.issues.append({
                            "type": "file_operation",
                            "severity": "medium",
                            "message": "File opened but may not be properly closed",
                            "file": self.current_file,
                            "line": node.lineno,
                            "suggestion": "Use 'with' statement for automatic file closing"
                        })
    
    def _check_numpy_operations(self, tree: ast.AST):
        """Check for NumPy operation issues."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if hasattr(node.func, 'value') and hasattr(node.func.value, 'id'):
                    if node.func.value.id == 'np':
                        if hasattr(node.func, 'attr') and node.func.attr in ['array', 'zeros', 'ones']:
                            # Check for large array creation
                            for arg in node.args:
                                if isinstance(arg, ast.Constant) and isinstance(arg.value, int):
                                    if arg.value > 1000000:
                                        self.issues.append({
                                            "type": "large_numpy_array",
                                            "severity": "medium",
                                            "message": f"Creating large NumPy array with size {arg.value}",
                                            "file": self.current_file,
                                            "line": node.lineno,
                                            "suggestion": "Consider memory usage and potential alternatives"
                                        })
    
    def _check_hdf5_operations(self, tree: ast.AST):
        """Check for HDF5 operation issues."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if hasattr(node.func, 'value') and hasattr(node.func.value, 'id'):
                    if node.func.value.id == 'h5py':
                        if hasattr(node.func, 'attr') and node.func.attr == 'File':
                            # Check if HDF5 file is properly closed
                            if not self._has_proper_hdf5_handling(node):
                                self.issues.append({
                                    "type": "hdf5_operation",
                                    "severity": "medium",
                                    "message": "HDF5 file opened but may not be properly closed",
                                    "file": self.current_file,
                                    "line": node.lineno,
                                    "suggestion": "Use 'with' statement for automatic HDF5 file closing"
                                })
    
    def _check_memory_leaks(self, tree: ast.AST):
        """Check for potential memory leaks."""
        # Look for large data structures that might not be cleaned up
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        if target.id in ['data', 'array', 'matrix', 'centroid']:
                            # Check if this is a large data assignment
                            if self._is_large_data_assignment(node.value):
                                self.issues.append({
                                    "type": "potential_memory_leak",
                                    "severity": "low",
                                    "message": f"Large data assigned to variable '{target.id}'",
                                    "file": self.current_file,
                                    "line": node.lineno,
                                    "suggestion": "Consider cleanup or memory management for large data structures"
                                })
    
    def _check_error_handling(self, tree: ast.AST):
        """Check for missing error handling."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if hasattr(node.func, 'id') and node.func.id in ['open', 'np.load', 'h5py.File']:
                    # Check if this call is in a try-except block
                    if not self._is_in_try_except(node):
                        self.issues.append({
                            "type": "missing_error_handling",
                            "severity": "medium",
                            "message": f"Call to {node.func.id} without error handling",
                            "file": self.current_file,
                            "line": node.lineno,
                            "suggestion": "Wrap in try-except block for better error handling"
                        })
    
    def _has_proper_file_handling(self, node: ast.Call) -> bool:
        """Check if file operation has proper handling."""
        # This is a simplified check - in practice, you'd need more sophisticated analysis
        return False
    
    def _has_proper_hdf5_handling(self, node: ast.Call) -> bool:
        """Check if HDF5 operation has proper handling."""
        # This is a simplified check - in practice, you'd need more sophisticated analysis
        return False
    
    def _is_large_data_assignment(self, node: ast.AST) -> bool:
        """Check if assignment involves large data."""
        # This is a simplified check - in practice, you'd need more sophisticated analysis
        return False
    
    def _is_in_try_except(self, node: ast.AST) -> bool:
        """Check if node is within a try-except block."""
        # This is a simplified check - in practice, you'd need more sophisticated analysis
        return False

def main():
    """Main function to run BugSpot analysis."""
    if len(sys.argv) < 2:
        print("Usage: python bugspot_analyzer.py <file_or_directory>")
        sys.exit(1)
    
    target = sys.argv[1]
    analyzer = MethylCentroidBugSpot()
    all_issues = []
    
    if Path(target).is_file():
        issues = analyzer.analyze_file(target)
        all_issues.extend(issues)
    elif Path(target).is_dir():
        for py_file in Path(target).rglob("*.py"):
            if not any(exclude in str(py_file) for exclude in ['__pycache__', '.pytest_cache', 'venv', '.venv']):
                issues = analyzer.analyze_file(str(py_file))
                all_issues.extend(issues)
    else:
        print(f"Error: {target} is not a valid file or directory")
        sys.exit(1)
    
    # Output results
    report = {
        "project": "MethylCentroid",
        "total_issues": len(all_issues),
        "issues": all_issues
    }
    
    print(json.dumps(report, indent=2))
    
    if all_issues:
        sys.exit(1)  # Exit with error code if issues found
    else:
        print("✅ No issues found!")

if __name__ == "__main__":
    main() 