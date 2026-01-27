"""
Configuration models for MethylMapper.

Note: These are pure Pydantic models (not database tables).
For database models, see models.py which uses SQLModel.
"""

import os
from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class AzureSQLConfig(BaseModel):
    """Azure SQL Database connection configuration."""
    
    server: str = Field(
        default="em-maindb.database.windows.net",
        description="Azure SQL Server hostname (e.g., your-server.database.windows.net)"
    )
    database: str = Field(
        default="STRING-DB",
        description="Database name"
    )
    username: str = Field(
        default="dba",
        description="Database username"
    )
    password: str = Field(
        default="",
        description="Database password (set via AZURE_SQL_PASSWORD env var or secure storage)"
    )
    driver: str = Field(
        default="ODBC Driver 18 for SQL Server",
        description="ODBC driver name"
    )
    port: int = Field(
        default=1433,
        description="Database port"
    )
    
    @model_validator(mode='after')
    def resolve_password(self):
        """Resolve password from environment variable or secure storage if not provided."""
        if not self.password:
            # Try environment variable first
            self.password = os.environ.get('AZURE_SQL_PASSWORD', '')
            
            # If still empty, try secure credential manager
            if not self.password:
                try:
                    from .secure_credentials import SecureCredentialManager
                    credential_manager = SecureCredentialManager(
                        credential_name="azure_sql_password",
                        env_var_name="AZURE_SQL_PASSWORD"
                    )
                    self.password = credential_manager.get_credential() or ''
                except Exception:
                    # If secure storage fails, leave empty (will fail at connection time)
                    pass
        
        return self
    
    def get_connection_string(self) -> str:
        """Build SQLAlchemy connection string for Azure SQL."""
        import urllib.parse
        
        # Build ODBC connection string
        odbc_str = (
            f"DRIVER={{{self.driver}}};"
            f"SERVER={self.server},{self.port};"
            f"DATABASE={self.database};"
            f"UID={self.username};"
            f"PWD={self.password};"
            "Encrypt=yes;"
            "TrustServerCertificate=no;"
            "Connection Timeout=30;"
        )
        
        # URL-encode for SQLAlchemy
        params = urllib.parse.quote_plus(odbc_str)
        return f"mssql+pyodbc:///?odbc_connect={params}"


class StoredProcedureConfig(BaseModel):
    """Configuration for spMapDMP2Genes stored procedure parameters."""
    param_id: int = Field(
        default=1,
        ge=1,
        description="dbo.params ID used by spMapDMP2Genes"
    )
    upstream_size: int = Field(
        default=5000,
        ge=0,
        description="Upstream region size for promoter mapping (bp)"
    )
    downstream_size: int = Field(
        default=2000,
        ge=0,
        description="Downstream region size for terminator mapping (bp)"
    )
    min_intron_size: int = Field(
        default=0,
        ge=0,
        description="Minimum intron size to consider (bp)"
    )
    w_promoter: float = Field(
        default=2.0,
        gt=0.0,
        description="Weight for promoter region DMPs"
    )
    w_terminator: float = Field(
        default=0.5,
        gt=0.0,
        description="Weight for terminator region DMPs"
    )
    w_gene_body: float = Field(
        default=1.0,
        gt=0.0,
        description="Weight for gene body DMPs"
    )
    w_exon: float = Field(
        default=1.5,
        gt=0.0,
        description="Weight for exon DMPs"
    )
    w_intron: float = Field(
        default=0.7,
        gt=0.0,
        description="Weight for intron DMPs"
    )
    w_unknown: float = Field(
        default=1.0,
        gt=0.0,
        description="Weight for unknown region DMPs"
    )
    
    @field_validator('upstream_size', 'downstream_size', 'min_intron_size')
    @classmethod
    def validate_sizes(cls, v):
        """Validate region sizes are reasonable."""
        if v > 1_000_000:  # 1 Mb
            raise ValueError(f"Region size {v} seems too large (max 1Mb)")
        return v


class MethylMapperConfig(BaseModel):
    """Complete configuration for MethylMapper."""
    
    database: AzureSQLConfig = Field(
        ...,
        description="Azure SQL Database connection configuration"
    )
    stored_procedure: StoredProcedureConfig = Field(
        default_factory=StoredProcedureConfig,
        description="Stored procedure parameters"
    )
    input_csv: Optional[str] = Field(
        default=None,
        description="Input DMP CSV file path"
    )
    output_csv: Optional[str] = Field(
        default="mapped_genes.csv",
        description="Output CSV file path for gene mapping results"
    )
    output_json: Optional[str] = Field(
        default="mapped_genes.json",
        description="Output JSON file path for gene names list"
    )
    sample_id: Optional[int] = Field(
        default=None,
        description="Sample ID for database tracking"
    )
    chromosome: Optional[str] = Field(
        default=None,
        description="Chromosome (override from CSV if specified)"
    )
    context: Optional[str] = Field(
        default=None,
        description="Context (override from CSV if specified)"
    )

