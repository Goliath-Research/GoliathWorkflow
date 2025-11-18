# Quick Reference: Methylation Contexts

## Your Config (Updated)

```json
{
  "chromosome": "1",
  "contexts": ["CG"],  // ← Using CG only for focused PCa signal
  ...
}
```

## Common Configurations

### Cancer/Biomarker Analysis (Recommended)
```json
"contexts": ["CG"]
```
✅ Strongest signal  
✅ Best for clinical biomarkers  
✅ Avoids signal dilution from CHG/CHH  

### Plant Biology
```json
"contexts": ["CG", "CHG", "CHH"],
"use_context_weights": true
```

### Compare Contexts Separately
```bash
# Run 1: CG only
"contexts": ["CG"], "output_dir": "/path/output_CG"

# Run 2: CHG only  
"contexts": ["CHG"], "output_dir": "/path/output_CHG"

# Run 3: CHH only
"contexts": ["CHH"], "output_dir": "/path/output_CHH"
```

## Expected Impact

**Previous (all contexts):**
- 90,100 → 962 DMPs
- 481 genes
- Effect size: 0.87
- Context mix: 78% CG, 9% CHG, 13% CHH

**New (CG only):**
- Expected: Stronger CG-specific signal
- Expected: More focused gene list
- Expected: Higher effect sizes
- Faster processing (3x)

## Run Updated Analysis

```bash
cd /home/ubuntu/MethylPipeline
python -m methyl_detector.cli.main \
    packages/methylmodeler/configs/pb-hc1-1_config.json
```

## More Info

- **Full guide**: `packages/methylmodeler/CONTEXT_SELECTION_GUIDE.md`
- **Templates**: `packages/methylmodeler/configs/TEMPLATE_*.json`
- **Changes summary**: `CONTEXT_PARAMETER_UPDATE.md`

