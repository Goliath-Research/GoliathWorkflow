# MethylMapper Installation Guide

## Prerequisites

Before installing MethylMapper, ensure you have:

1. **Python 3.8 or higher**
2. **pip** (Python package manager)
3. **ODBC Driver 17 for SQL Server** (or compatible)
4. **Azure SQL Database** access with credentials
5. **Network access** to Azure SQL (firewall rules configured)

## Step 1: Install ODBC Driver

### Ubuntu/Debian

```bash
# Add Microsoft repository
curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -
curl https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list | \
    sudo tee /etc/apt/sources.list.d/mssql-release.list

# Update package list
sudo apt-get update

# Install ODBC Driver 17
sudo ACCEPT_EULA=Y apt-get install -y msodbcsql17

# Install unixODBC development headers (required for pyodbc)
sudo apt-get install -y unixodbc-dev

# Verify installation
odbcinst -j
```

### macOS

```bash
# Install using Homebrew
brew tap microsoft/mssql-release https://github.com/Microsoft/homebrew-mssql-release
brew update
brew install msodbcsql17

# Verify installation
odbcinst -j
```

### Windows

1. Download ODBC Driver 17 from [Microsoft Download Center](https://docs.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)
2. Run the installer
3. Follow installation wizard

## Step 2: Install MethylMapper

### From Source (Recommended for Development)

```bash
# Clone or navigate to MethylMapper directory
cd /home/ubuntu/MethylMapper

# Install in editable mode
pip install -e .
```

### Install Dependencies Only

```bash
cd /home/ubuntu/MethylMapper
pip install -r requirements.txt
```

## Step 3: Verify Installation

### Check MethylMapper Installation

```bash
# Test CLI is available
methyl_mapper --version

# Should output: MethylMapper 0.1.0
```

### Test Python Import

```bash
python -c "from methyl_mapper import DMPMapper, MethylMapperConfig; print('✓ MethylMapper installed successfully')"
```

### Test ODBC Driver

```bash
python -c "import pyodbc; print('Available drivers:', pyodbc.drivers())"
```

You should see "ODBC Driver 17 for SQL Server" in the list.

## Step 4: Configure Database Access

### Create Configuration File

Create a configuration file with your Azure SQL credentials:

```bash
cd /home/ubuntu/MethylMapper
cp example_config.json my_config.json
```

Edit `my_config.json` with your credentials:

```json
{
  "database": {
    "server": "your-server.database.windows.net",
    "database": "your_database",
    "username": "your_username",
    "password": "your_password",
    "driver": "ODBC Driver 17 for SQL Server",
    "port": 1433
  },
  "stored_procedure": {
    "upstream_size": 5000,
    "downstream_size": 2000,
    "min_intron_size": 0,
    "w_promoter": 2.0,
    "w_terminator": 0.5,
    "w_gene_body": 1.0,
    "w_exon": 1.5,
    "w_intron": 0.7,
    "w_unknown": 1.0
  }
}
```

### Test Database Connection

```bash
python -c "
from methyl_mapper import MethylMapperConfig, AzureSQLConnection
config = MethylMapperConfig.parse_file('my_config.json')
with AzureSQLConnection(config.database) as db:
    print('✓ Database connection successful')
"
```

## Step 5: Set Up Database Schema

### Create Staging Table

Connect to your Azure SQL Database and run:

```sql
CREATE TABLE dmp_staging (
    SampleID INT NOT NULL,
    position BIGINT NOT NULL,
    chromosome VARCHAR(10) NOT NULL,
    context VARCHAR(3) NOT NULL,
    q_value FLOAT NULL,
    delta_mean FLOAT NULL,
    overlap FLOAT NULL,
    effect_size FLOAT NULL,
    INDEX IX_dmp_staging_SampleID (SampleID)
);
```

### Verify Stored Procedure

Ensure `spMapDMP2Genes` exists in your database:

```sql
SELECT OBJECT_ID('dbo.spMapDMP2Genes', 'P');
```

If NULL, the stored procedure doesn't exist and needs to be created.

## Step 6: Test Complete Pipeline

### Create Test DMP CSV

Create a small test file `test_dmps.csv`:

```csv
position,chromosome,context,q_value,delta_mean,overlap,effect_size
12345,chr1,CG,0.001,0.45,0.15,125.3
12346,chr1,CG,0.002,0.38,0.20,98.7
12347,chr1,CG,0.003,0.42,0.18,110.5
```

### Run Test Mapping

```bash
methyl_mapper --input test_dmps.csv \
             --config my_config.json \
             --sample-id 99999 \
             --verbose
```

Expected output:
```
[INFO] Loading DMPs from test_dmps.csv...
[INFO] ✅ Loaded 3 DMPs from CSV
[INFO] Connecting to Azure SQL: your-server.database.windows.net/your_database
[INFO] ✅ Connected to Azure SQL Server
[INFO] Uploading 3 DMPs for SampleID=99999...
[INFO] ✅ Uploaded 3 DMPs to staging table
[INFO] Executing spMapDMP2Genes for SampleID=99999, chr1-CG...
[INFO] ✅ Stored procedure returned N gene mappings
[INFO] ✅ Saved full results to mapped_genes.csv (N rows)
[INFO] ✅ Saved gene names to mapped_genes.json (N unique genes)
```

## Troubleshooting

### Issue: "ODBC Driver Not Found"

**Symptoms**:
```
pyodbc.Error: ('01000', "[01000] [unixODBC][Driver Manager]Can't open lib 'ODBC Driver 17 for SQL Server'")
```

**Solutions**:
1. Verify ODBC driver is installed: `odbcinst -q -d`
2. Check driver name in config matches installed driver exactly
3. Reinstall ODBC driver
4. Try alternative driver name: "ODBC Driver 18 for SQL Server"

### Issue: "Cannot Connect to Azure SQL"

**Symptoms**:
```
sqlalchemy.exc.OperationalError: (pyodbc.OperationalError) ('08001', '[08001] ...')
```

**Solutions**:
1. Check server name includes `.database.windows.net`
2. Verify firewall allows your IP address:
   - Azure Portal → SQL Server → Firewalls and virtual networks
   - Add your IP address
3. Test with `sqlcmd`:
   ```bash
   sqlcmd -S your-server.database.windows.net -U your_username -P your_password -d your_database
   ```
4. Verify credentials are correct
5. Check network connectivity:
   ```bash
   telnet your-server.database.windows.net 1433
   ```

### Issue: "pyodbc Not Found"

**Symptoms**:
```
ModuleNotFoundError: No module named 'pyodbc'
```

**Solutions**:
```bash
pip install pyodbc
```

If compilation fails, install development headers:
```bash
# Ubuntu/Debian
sudo apt-get install -y unixodbc-dev python3-dev

# macOS
brew install unixodbc
```

### Issue: "Permission Denied on Stored Procedure"

**Symptoms**:
```
sqlalchemy.exc.ProgrammingError: ... EXECUTE permission was denied on the object 'spMapDMP2Genes'
```

**Solutions**:
1. Grant EXECUTE permission:
   ```sql
   GRANT EXECUTE ON dbo.spMapDMP2Genes TO your_username;
   ```
2. Verify permissions:
   ```sql
   SELECT * FROM fn_my_permissions('dbo.spMapDMP2Genes', 'OBJECT');
   ```

### Issue: "Table dmp_staging Does Not Exist"

**Symptoms**:
```
sqlalchemy.exc.ProgrammingError: ... Invalid object name 'dmp_staging'
```

**Solutions**:
1. MethylMapper should create table automatically
2. Manually create table (see Step 5 above)
3. Verify you're connected to correct database
4. Check user has CREATE TABLE permission

### Issue: "Missing Required Columns"

**Symptoms**:
```
ValueError: Missing required columns: ['effect_size']
```

**Solutions**:
1. Ensure input CSV is from MethylDetector v0.2.0+
2. Check column names match exactly (case-sensitive)
3. Verify CSV is not corrupted:
   ```bash
   head -5 your_dmps.csv
   ```

## Advanced Configuration

### Using Environment Variables

Instead of storing passwords in JSON:

```bash
export AZURE_SQL_PASSWORD="your_password"
```

Then in Python:

```python
import os
import json

config_dict = json.load(open('config.json'))
config_dict['database']['password'] = os.environ['AZURE_SQL_PASSWORD']
config = MethylMapperConfig(**config_dict)
```

### Using Azure Key Vault

For production environments:

```python
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

# Get password from Key Vault
credential = DefaultAzureCredential()
client = SecretClient(vault_url="https://your-vault.vault.azure.net/", credential=credential)
password = client.get_secret("sql-password").value

# Use in config
config_dict['database']['password'] = password
```

### Connection String Customization

Modify `config.py` `get_connection_string()` method for custom connection parameters.

## Uninstallation

```bash
pip uninstall methyl_mapper
```

## Next Steps

1. **Run with MethylDetector output**:
   ```bash
   methyl_mapper --input ../MethylDetector/output/biological_dmps-chr1-CG.csv \
                --config my_config.json \
                --sample-id 12345
   ```

2. **Use mapped genes for enrichment**:
   ```bash
   cd /home/ubuntu/MethylEnricher
   methylenricher --input ../MethylMapper/mapped_genes.json \
                  --outdir enrichment_results
   ```

3. **Automate with scripts**:
   - Create pipeline scripts
   - Use with batch processing
   - Integrate with workflow managers

## Support

For installation issues:
- Check this guide thoroughly
- Review error messages carefully
- Check Azure SQL firewall and permissions
- Verify ODBC driver installation
- Contact the MethylDetector team

## Additional Resources

- [Azure SQL Database Documentation](https://docs.microsoft.com/azure/azure-sql/)
- [ODBC Driver for SQL Server](https://docs.microsoft.com/sql/connect/odbc/microsoft-odbc-driver-for-sql-server)
- [pyodbc Documentation](https://github.com/mkleehammer/pyodbc/wiki)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)

