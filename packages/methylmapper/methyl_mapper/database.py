"""
Azure SQL Database connection and operations for MethylMapper.

Uses SQLModel for ORM operations, combining Pydantic validation and SQLAlchemy power.
"""

import logging
from typing import List, Optional
import pandas as pd
from sqlmodel import SQLModel, Session, create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool

from .config import AzureSQLConfig, StoredProcedureConfig
from .models import DMPStaging

logger = logging.getLogger(__name__)


class AzureSQLConnection:
    """
    Manages Azure SQL Database connection and operations for DMP-to-gene mapping.
    
    Uses SQLModel for ORM operations and pandas for bulk data handling.
    """
    
    def __init__(self, config: AzureSQLConfig):
        """
        Initialize connection manager.
        
        Args:
            config: Azure SQL connection configuration
        """
        self.config = config
        self.engine: Optional[Engine] = None
    
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
            with Session(self.engine) as session:
                result = session.exec(text("SELECT @@VERSION")).one()
                logger.info(f"✅ Connected to Azure SQL Server")
                logger.debug(f"Server version: {result[:100]}...")
                
        except Exception as e:
            logger.error(f"Failed to connect to Azure SQL: {e}")
            raise
    
    def create_tables(self) -> None:
        """
        Create all SQLModel tables in the database if they don't exist.
        This is the SQLModel way - much simpler than manual table creation!
        """
        if self.engine is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        try:
            logger.info("Ensuring database tables exist...")
            SQLModel.metadata.create_all(self.engine)
            logger.info("✅ Database tables ready")
        except Exception as e:
            logger.error(f"Failed to create tables: {e}")
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
            with Session(self.engine) as session:
                # Use SQLModel ORM query
                statement = select(DMPStaging).where(DMPStaging.SampleID == sample_id)
                results = session.exec(statement).all()
                
                deleted_count = len(results)
                
                # Delete the records
                for record in results:
                    session.delete(record)
                
                session.commit()
                
                if deleted_count > 0:
                    logger.info(f"Cleared {deleted_count} existing rows for SampleID={sample_id}")
                return deleted_count
                
        except Exception as e:
            logger.error(f"Failed to clear sample data: {e}")
            raise
    
    def upload_dmps(self, dmps_df: pd.DataFrame, sample_id: int) -> int:
        """
        Upload DMPs to staging table using bulk insert.
        
        Args:
            dmps_df: DataFrame with DMP data
                     Required columns: position, chromosome, context
                     Optional columns: q_value, delta_mean, overlap, effect_size
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
            
            # Validate required columns
            required_cols = ['position', 'chromosome', 'context']
            missing_cols = [col for col in required_cols if col not in upload_df.columns]
            if missing_cols:
                raise ValueError(f"Missing required columns: {missing_cols}")
            
            # Optional columns (fill with None if missing)
            optional_cols = ['q_value', 'delta_mean', 'overlap', 'effect_size']
            for col in optional_cols:
                if col not in upload_df.columns:
                    upload_df[col] = None
            
            # Select columns in the order expected by the model
            db_cols = ['SampleID', 'position', 'chromosome', 'context', 
                      'q_value', 'delta_mean', 'overlap', 'effect_size']
            upload_df = upload_df[db_cols]
            
            # Upload using pandas to_sql (fast bulk insert)
            # Note: pandas to_sql doesn't go through SQLModel validation,
            # but it's much faster for bulk operations
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
    
    def upload_dmps_orm(self, dmps: List[DMPStaging]) -> int:
        """
        Upload DMPs using SQLModel ORM (slower but validates through Pydantic).
        
        Use this when you need full validation. For bulk operations, use upload_dmps().
        
        Args:
            dmps: List of DMPStaging objects
            
        Returns:
            Number of rows uploaded
        """
        if self.engine is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        try:
            logger.info(f"Uploading {len(dmps):,} DMPs using ORM...")
            
            with Session(self.engine) as session:
                # Add all records
                for dmp in dmps:
                    session.add(dmp)
                
                # Commit in one transaction
                session.commit()
            
            logger.info(f"✅ Uploaded {len(dmps):,} DMPs via ORM")
            return len(dmps)
            
        except Exception as e:
            logger.error(f"Failed to upload DMPs via ORM: {e}")
            raise
    
    def get_sample_dmps(self, sample_id: int) -> List[DMPStaging]:
        """
        Retrieve all DMPs for a sample using SQLModel ORM.
        
        Args:
            sample_id: Sample ID to retrieve
            
        Returns:
            List of DMPStaging objects
        """
        if self.engine is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        try:
            with Session(self.engine) as session:
                statement = select(DMPStaging).where(DMPStaging.SampleID == sample_id)
                results = session.exec(statement).all()
                return list(results)
        except Exception as e:
            logger.error(f"Failed to retrieve sample DMPs: {e}")
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
            
            # Execute and fetch results using SQLModel Session
            with Session(self.engine) as session:
                result = session.exec(sp_call, params=params)
                
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
        """Close database connection and dispose of engine."""
        if self.engine is not None:
            self.engine.dispose()
            logger.info("Database connection closed")
            self.engine = None
    
    def __enter__(self):
        """Context manager entry - automatically connects."""
        self.connect()
        self.create_tables()  # Ensure tables exist
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - automatically closes."""
        self.close()
