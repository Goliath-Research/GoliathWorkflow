"""
Azure SQL Database connection and operations for MethylMapper
"""

import logging
from typing import Dict, List, Any, Optional
import pandas as pd
from sqlalchemy import create_engine, text, Table, Column, Integer, BigInteger, String, Float, MetaData
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool

from .config import AzureSQLConfig, StoredProcedureConfig

logger = logging.getLogger(__name__)


class AzureSQLConnection:
    """
    Manages Azure SQL Database connection and operations for DMP-to-gene mapping.
    
    Uses SQLAlchemy for connection management and pandas for bulk data operations.
    """
    
    def __init__(self, config: AzureSQLConfig):
        """
        Initialize connection manager.
        
        Args:
            config: Azure SQL connection configuration
        """
        self.config = config
        self.engine: Optional[Engine] = None
        self.metadata = MetaData()
        
        # Define staging table structure
        self.dmp_staging_table = Table(
            'dmp_staging',
            self.metadata,
            Column('SampleID', Integer, nullable=False),
            Column('position', BigInteger, nullable=False),
            Column('chromosome', String(10), nullable=False),
            Column('context', String(3), nullable=False),
            Column('q_value', Float, nullable=True),
            Column('delta_mean', Float, nullable=True),
            Column('overlap', Float, nullable=True),
            Column('effect_size', Float, nullable=True),
        )
    
    def connect(self) -> None:
        """
        Establish connection to Azure SQL Database.
        
        Raises:
            Exception: If connection fails
        """
        try:
            connection_string = self.config.get_connection_string()
            logger.info(f"Connecting to Azure SQL: {self.config.server}/{self.config.database}")
            
            # Create engine with connection pooling disabled for Azure SQL
            self.engine = create_engine(
                connection_string,
                poolclass=NullPool,  # Disable pooling for Azure SQL compatibility
                echo=False
            )
            
            # Test connection
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT @@VERSION"))
                version = result.fetchone()[0]
                logger.info(f"✅ Connected to Azure SQL Server")
                logger.debug(f"Server version: {version[:100]}...")
                
        except Exception as e:
            logger.error(f"Failed to connect to Azure SQL: {e}")
            raise
    
    def ensure_staging_table_exists(self) -> None:
        """
        Ensure the dmp_staging table exists in the database.
        Creates it if it doesn't exist.
        """
        if self.engine is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        try:
            # Check if table exists
            with self.engine.connect() as conn:
                result = conn.execute(text(
                    "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
                    "WHERE TABLE_NAME = 'dmp_staging'"
                ))
                exists = result.fetchone()[0] > 0
                
                if not exists:
                    logger.info("Creating dmp_staging table...")
                    self.metadata.create_all(self.engine, tables=[self.dmp_staging_table])
                    logger.info("✅ dmp_staging table created")
                else:
                    logger.debug("dmp_staging table already exists")
                    
        except Exception as e:
            logger.error(f"Failed to ensure staging table exists: {e}")
            raise
    
    def clear_sample_data(self, sample_id: int) -> int:
        """
        Clear existing data for a sample ID from staging table.
        
        Args:
            sample_id: Sample ID to clear
            
        Returns:
            Number of rows deleted
        """
        if self.engine is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    text("DELETE FROM dmp_staging WHERE SampleID = :sample_id"),
                    {"sample_id": sample_id}
                )
                conn.commit()
                deleted = result.rowcount
                if deleted > 0:
                    logger.info(f"Cleared {deleted} existing rows for SampleID={sample_id}")
                return deleted
        except Exception as e:
            logger.error(f"Failed to clear sample data: {e}")
            raise
    
    def upload_dmps(self, dmps_df: pd.DataFrame, sample_id: int) -> int:
        """
        Upload DMPs to staging table using bulk insert.
        
        Args:
            dmps_df: DataFrame with DMP data (must have: position, chromosome, context, q_value, delta_mean, overlap, effect_size)
            sample_id: Sample ID for tracking
            
        Returns:
            Number of rows uploaded
        """
        if self.engine is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        try:
            # Prepare DataFrame for upload
            upload_df = dmps_df.copy()
            upload_df['SampleID'] = sample_id
            
            # Select and rename columns to match staging table
            required_cols = ['SampleID', 'position', 'chromosome', 'context', 'q_value', 'delta_mean', 'overlap', 'effect_size']
            
            # Ensure all required columns exist
            missing_cols = [col for col in required_cols if col not in upload_df.columns]
            if missing_cols:
                raise ValueError(f"Missing required columns: {missing_cols}")
            
            upload_df = upload_df[required_cols]
            
            # Upload using pandas to_sql (fast bulk insert)
            logger.info(f"Uploading {len(upload_df):,} DMPs for SampleID={sample_id}...")
            
            upload_df.to_sql(
                name='dmp_staging',
                con=self.engine,
                if_exists='append',
                index=False,
                method='multi',
                chunksize=1000
            )
            
            logger.info(f"✅ Uploaded {len(upload_df):,} DMPs to staging table")
            return len(upload_df)
            
        except Exception as e:
            logger.error(f"Failed to upload DMPs: {e}")
            raise
    
    def execute_stored_procedure(
        self,
        sample_id: int,
        chromosome: str,
        context: str,
        sp_config: StoredProcedureConfig
    ) -> pd.DataFrame:
        """
        Execute spMapDMP2Genes stored procedure and return results.
        
        Args:
            sample_id: Sample ID to process
            chromosome: Chromosome identifier
            context: Methylation context (e.g., CG, CHG, CHH)
            sp_config: Stored procedure parameters
            
        Returns:
            DataFrame with gene mapping results
        """
        if self.engine is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        try:
            logger.info(f"Executing spMapDMP2Genes for SampleID={sample_id}, {chromosome}-{context}...")
            
            # Build stored procedure call
            sp_call = text("""
                EXEC spMapDMP2Genes
                    @SampleID = :sample_id,
                    @chromosome = :chromosome,
                    @context = :context,
                    @upstream_size = :upstream_size,
                    @downstream_size = :downstream_size,
                    @min_intron_size = :min_intron_size,
                    @w_promoter = :w_promoter,
                    @w_terminator = :w_terminator,
                    @w_gene_body = :w_gene_body,
                    @w_exon = :w_exon,
                    @w_intron = :w_intron,
                    @w_unknown = :w_unknown
            """)
            
            params = {
                'sample_id': sample_id,
                'chromosome': chromosome,
                'context': context,
                'upstream_size': sp_config.upstream_size,
                'downstream_size': sp_config.downstream_size,
                'min_intron_size': sp_config.min_intron_size,
                'w_promoter': sp_config.w_promoter,
                'w_terminator': sp_config.w_terminator,
                'w_gene_body': sp_config.w_gene_body,
                'w_exon': sp_config.w_exon,
                'w_intron': sp_config.w_intron,
                'w_unknown': sp_config.w_unknown
            }
            
            # Execute and fetch results
            with self.engine.connect() as conn:
                result = conn.execute(sp_call, params)
                
                # Fetch all rows
                rows = result.fetchall()
                if not rows:
                    logger.warning("Stored procedure returned no results")
                    return pd.DataFrame()
                
                # Convert to DataFrame
                columns = result.keys()
                df = pd.DataFrame(rows, columns=columns)
                
                logger.info(f"✅ Stored procedure returned {len(df):,} gene mappings")
                return df
                
        except Exception as e:
            logger.error(f"Failed to execute stored procedure: {e}")
            raise
    
    def close(self) -> None:
        """Close database connection."""
        if self.engine is not None:
            self.engine.dispose()
            logger.info("Database connection closed")
            self.engine = None
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

