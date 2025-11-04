"""
MethylMapper - DMP to gene mapping using Azure SQL Database

This package provides tools for mapping Differentially Methylated Positions (DMPs)
to genes using STRING-DB via Azure SQL stored procedures.

Also includes bedtools-based mapping for local analysis without database requirements.
"""

from .config import MethylMapperConfig, AzureSQLConfig, StoredProcedureConfig
from .database import AzureSQLConnection
from .models import DMPStaging, GeneMappingResult
from .mapper import DMPMapper
from .bedtools_mapper import BedtoolsMapper
from .gene_disease_enricher import GeneDiseaseEnricher
from .secure_credentials import SecureCredentialManager

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
    "BedtoolsMapper",
    "GeneDiseaseEnricher",
    "SecureCredentialManager",
]

