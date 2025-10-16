"""
MethylMapper - DMP to gene mapping using Azure SQL Database

This package provides tools for mapping Differentially Methylated Positions (DMPs)
to genes using STRING-DB via Azure SQL stored procedures.

Uses SQLModel for clean ORM operations with Pydantic validation.
"""

from .config import MethylMapperConfig, AzureSQLConfig, StoredProcedureConfig
from .database import AzureSQLConnection
from .models import DMPStaging, GeneMappingResult
from .mapper import DMPMapper

__version__ = "0.1.0"
__all__ = [
    # Configuration
    "MethylMapperConfig",
    "AzureSQLConfig",
    "StoredProcedureConfig",
    # Database
    "AzureSQLConnection",
    # Models
    "DMPStaging",
    "GeneMappingResult",
    # High-level API
    "DMPMapper",
]

