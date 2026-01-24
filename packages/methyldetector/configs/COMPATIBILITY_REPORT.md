# MethylModeler Config Compatibility Report for create_all_models.py

## Summary
All **22 JSON config files** in the MethylModeler configs directory are compatible with `create_all_models.py`.

## Compatibility Status

### ✓ All Configs Are Compatible

The `create_all_models.py` script supports three config formats:

1. **Format 1**: Configs with `chromosome` (singular) + `contexts` fields
2. **Format 2**: Configs with `centroid1_dir` + `centroid2_dir` fields  
3. **Format 3**: Configs with `centroid1_path` + `centroid2_path` fields (converted to Format 2)

## Config Breakdown by Format

### Format 1: chromosome + contexts (5 configs)
- `multi-context-example.json`
- `pb-hc1-1-fresh-frozen_config.json`
- `pb-hc1-1-prepilot_config.json`
- `pb-hc1-1_config.json`
- `pb-hc_config.json`
- `pc-hc_config.json`

### Format 2: centroid1_dir + centroid2_dir (4 configs)
- `pb-ch_config.json` ⚠️ (also has `chromosomes` plural field)
- `pb-hc1-1_metadata_validation.json`
- `WT-msh1_config.json` ⚠️ (also has `chromosomes` as string)

### Format 3: centroid1_path + centroid2_path → converted (12 configs)
- `WT-msh1-1-CG_config.json`
- `fdr_methods_example.json`
- `methyl_modeler_example.json`
- `pb-c1c2-1-CG_config.json`
- `pb-ch-1-CG_config.json`
- `pb-hc1-1-CG_config.json`
- `pb-hc12-1-CG_config.json`
- `pb-hc2-1-CG_config.json`
- `pb-hc2A-1-CG_config.json`
- `pb-hc2B-1-CG_config.json`
- `pb-hc2C-1-CG_config.json`
- `pb-hc34-1-CG_config.json`
- `pp-ch-1-CG_config.json`

## Important Notes

### ⚠️ Potential Issues

1. **`pb-ch_config.json`** and **`WT-msh1_config.json`**:
   - These configs have `chromosomes` (plural) field instead of `chromosome` (singular)
   - The script will add a `chromosome` field for processing
   - The original `chromosomes` field will remain in the config (shallow copy)
   - **Action**: The `chromosomes` field should be removed or ignored by the md script

2. **Context Overwriting**:
   - Configs with Format 2 that have existing `contexts` will have their contexts replaced with `['CG', 'CHG', 'CHH']` by default
   - This is intentional behavior to process all contexts per chromosome

3. **Format 3 Conversion**:
   - Old format configs using `centroid1_path`/`centroid2_path` are automatically converted
   - The parent directory is extracted and used as `centroid1_dir`/`centroid2_dir`
   - The old path fields are removed from the config

## How create_all_models.py Works

1. Reads the input config file
2. Extracts the original chromosome (if present) and removes it from processing list
3. For each remaining chromosome (1-22, X, Y):
   - Creates a modified config with the chromosome and all contexts (CG, CHG, CHH)
   - Executes the `md` script with the modified config
   - Logs output to `output-{chromosome}.log`

## Recommendation

All configs can be used with `create_all_models.py`. The script handles the three formats correctly. If you encounter issues with configs that have both `chromosome` and `chromosomes` fields, you may want to add explicit handling to remove the `chromosomes` field when `chromosome` is set.

