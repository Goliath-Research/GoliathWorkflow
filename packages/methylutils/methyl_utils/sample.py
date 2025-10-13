"""
MethylSample class for handling methylation data samples and centroids.

This class provides a unified interface for individual samples and aggregated centroids,
with support for loading/saving HDF5 files, validation, and operations like masking/slicing.
"""

from typing import Union, Optional, Dict, Any
import numpy as np
import h5py
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class MethylSample:
    """
    Unified class for methylation samples (individual or aggregated centroids).
    
    Supports:
    - Basic samples: pos, mC, uC, tnc
    - Basic centroids: + N (sample count)
    - Extended centroids: + Sx, Sx2, log_x_sum, log_1_minus_x_sum (sufficient statistics)
    
    All arrays are numpy (uint32/float32 for efficiency).
    """
    
    def __init__(
        self,
        pos: np.ndarray,
        mC: np.ndarray,
        uC: np.ndarray,
        tnc: Optional[np.ndarray] = None,
        N: Optional[np.ndarray] = None,
        Sx: Optional[np.ndarray] = None,
        Sx2: Optional[np.ndarray] = None,
        log_x_sum: Optional[np.ndarray] = None,
        log_1_minus_x_sum: Optional[np.ndarray] = None
    ):
        """
        Initialize MethylSample with array data.
        
        Args:
            pos: Genomic positions (uint32, sorted unique).
            mC: Methylated counts (uint32).
            uC: Unmethylated counts (uint32).
            tnc: Third nucleotide context bytes (uint8, optional).
            N: Sample counts for centroids (uint32, optional).
            Sx: Sum of methylation levels for extended centroids (float32, optional).
            Sx2: Sum of squared methylation levels (float32, optional).
            log_x_sum: Sum of log(methylation) (float32, optional).
            log_1_minus_x_sum: Sum of log(1-methylation) (float32, optional).
        
        Raises:
            ValueError: If arrays have mismatched lengths or invalid data.
        """
        if len(pos) != len(mC) or len(pos) != len(uC):
            raise ValueError("All core arrays (pos, mC, uC) must have the same length.")
        
        self.pos = pos.astype(np.uint32)
        self.mC = mC.astype(np.uint32)
        self.uC = uC.astype(np.uint32)
        self.tnc = np.zeros(len(pos), dtype=np.uint8) if tnc is None else tnc.astype(np.uint8)
        
        # Centroid fields (None if not present)
        self.N = N.astype(np.uint32) if N is not None else None
        self.Sx = Sx.astype(np.float32) if Sx is not None else None
        self.Sx2 = Sx2.astype(np.float32) if Sx2 is not None else None
        self.log_x_sum = log_x_sum.astype(np.float32) if log_x_sum is not None else None
        self.log_1_minus_x_sum = log_1_minus_x_sum.astype(np.float32) if log_1_minus_x_sum is not None else None
        
        # Validate lengths for optional fields
        optional_fields = [self.N, self.Sx, self.Sx2, self.log_x_sum, self.log_1_minus_x_sum]
        for field in optional_fields:
            if field is not None and len(field) != len(self.pos):
                raise ValueError(f"Optional field has mismatched length: {len(field)} vs {len(self.pos)}")
        
        # Ensure positions are sorted and unique
        if not np.all(np.diff(self.pos) > 0):
            raise ValueError("Positions must be sorted and unique.")
        
        logger.debug(f"Created MethylSample with {len(self.pos)} positions (centroid: {self.is_centroid})")
    
    @classmethod
    def load_from_h5(cls, filepath: Union[str, Path]) -> 'MethylSample':
        """
        Load MethylSample from HDF5 file.
        
        Supports basic, basic_centroid, and extended_centroid formats.
        
        Args:
            filepath: Path to HDF5 file.
        
        Returns:
            Loaded MethylSample instance.
        
        Raises:
            ValueError: If file format invalid or missing required fields.
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        
        with h5py.File(path, 'r') as f:
            # Core fields (always present)
            pos = np.array(f['pos'], dtype=np.uint32)
            mC = np.array(f['mC'], dtype=np.uint32)
            uC = np.array(f['uC'], dtype=np.uint32)
            tnc = np.array(f.get('tnc', np.zeros(len(pos), dtype=np.uint8)), dtype=np.uint8)
            
            # Optional centroid fields
            N = np.array(f.get('N', None), dtype=np.uint32) if 'N' in f else None
            Sx = np.array(f.get('Sx', None), dtype=np.float32) if 'Sx' in f else None
            Sx2 = np.array(f.get('Sx2', None), dtype=np.float32) if 'Sx2' in f else None
            log_x_sum = np.array(f.get('log_x_sum', None), dtype=np.float32) if 'log_x_sum' in f else None
            log_1_minus_x_sum = np.array(f.get('log_1_minus_x_sum', None), dtype=np.float32) if 'log_1_minus_x_sum' in f else None
            
        return cls(pos, mC, uC, tnc, N, Sx, Sx2, log_x_sum, log_1_minus_x_sum)
    
    def save_to_h5(self, filepath: Union[str, Path]) -> None:
        """
        Save MethylSample to HDF5 file.
        
        Args:
            filepath: Output path.
        """
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with h5py.File(path, 'w') as f:
            f.create_dataset('pos', data=self.pos)
            f.create_dataset('mC', data=self.mC)
            f.create_dataset('uC', data=self.uC)
            f.create_dataset('tnc', data=self.tnc)
            
            if self.N is not None:
                f.create_dataset('N', data=self.N)
            if self.Sx is not None:
                f.create_dataset('Sx', data=self.Sx)
            if self.Sx2 is not None:
                f.create_dataset('Sx2', data=self.Sx2)
            if self.log_x_sum is not None:
                f.create_dataset('log_x_sum', data=self.log_x_sum)
            if self.log_1_minus_x_sum is not None:
                f.create_dataset('log_1_minus_x_sum', data=self.log_1_minus_x_sum)
        
        logger.info(f"Saved MethylSample to {path}")
    
    @property
    def is_centroid(self) -> bool:
        """Check if this is a centroid (has N field)."""
        return self.N is not None
    
    @property
    def is_extended_centroid(self) -> bool:
        """Check if this is an extended centroid (has N, Sx, Sx2, log sums)."""
        return (
            self.is_centroid and
            self.Sx is not None and self.Sx2 is not None and
            self.log_x_sum is not None and self.log_1_minus_x_sum is not None
        )
    
    # Additional methods can be added here (e.g., compute_mean, validate_coverage)