"""
MethylMapper - DMP to gene mapping using Azure SQL Database

This package provides tools for mapping Differentially Methylated Positions (DMPs)
to genes using STRING-DB via Azure SQL stored procedures.
"""

from .config import MethylMapperConfig, AzureSQLConfig, StoredProcedureConfig
from .database import AzureSQLConnection
from .mapper import DMPMapper

__version__ = "0.1.0"
__all__ = [
    "MethylMapperConfig",
    "AzureSQLConfig",
    "StoredProcedureConfig",
    "AzureSQLConnection",
    "DMPMapper",
]

