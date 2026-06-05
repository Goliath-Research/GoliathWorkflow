For **tumor detection**, cfDNA methylation is generally a **better** and more direct analyte than buffy‑coat methylation, but each has distinct strengths and use‑cases. [pmc.ncbi.nlm.nih](https://pmc.ncbi.nlm.nih.gov/articles/PMC6896050/)

### cfDNA methylation (plasma)

- Captures DNA shed from tumor tissue into circulation, so methylation patterns can be **tumor‑derived** and informative about tissue of origin. [pnas](https://www.pnas.org/doi/10.1073/pnas.2209852119)
- Multiple multi‑cancer early detection (MCED) tests using cfDNA methylation achieve high AUCs (often ≥0.90) for detecting various cancers and even localizing the primary site. [sciencedirect](https://www.sciencedirect.com/science/article/pii/S153561082200513X)
- Works well in principle for prostate and other solid tumors, especially when integrating fragmentomics with methylation to boost sensitivity at low tumor fractions. [academic.oup](https://academic.oup.com/clinchem/article/70/11/1355/7744959)
- Main limitations: low tumor fraction in early‑stage disease, higher sequencing depth and assay complexity, and stringent pre‑analytical requirements (timing, tubes, processing). [cd-genomics](https://www.cd-genomics.com/epigenetics/resource-cfdna-methylation-sequencing-methods-database-function.html)

### Buffy‑coat methylation (leukocyte DNA)

- Reflects **host/systemic** epigenetic changes (immune activation, inflammation, aging, exposures, comorbidities) that correlate with cancer risk or presence, but is usually **indirect**, not tumor DNA. [pmc.ncbi.nlm.nih](https://pmc.ncbi.nlm.nih.gov/articles/PMC6896050/)
- Easier to collect and process (whole blood, standard EDTA, no plasma separation) and gives abundant DNA, which is why many epidemiologic risk‑score studies use leukocyte methylation. [pmc.ncbi.nlm.nih](https://pmc.ncbi.nlm.nih.gov/articles/PMC6896050/)
- Signals can be stable and predictive at a population level but may be less specific to tumor type; strong confounding by cell‑type composition and environmental factors is common. [cd-genomics](https://www.cd-genomics.com/epigenetics/resource-cfdna-methylation-sequencing-methods-database-function.html)

### Which is “better” depends on your goal

- **Early detection / MCED, tumor localization, monitoring response or MRD** → cfDNA methylation is preferred because it tracks tumor‑derived patterns and can be combined with fragmentomic and nucleosome signatures for high sensitivity. [sciencedirect](https://www.sciencedirect.com/science/article/pii/S153561082200513X)
- **Risk stratification, host‑response signatures, or large, lower‑cost epidemiologic screening** → buffy‑coat methylation can be useful as a surrogate of systemic susceptibility or chronic inflammation but is less specific and less mechanistically tied to tumor biology. [cd-genomics](https://www.cd-genomics.com/epigenetics/resource-cfdna-methylation-sequencing-methods-database-function.html)

Given your current buffy‑coat EPIC pipeline, the most productive path for **cancer detection** would usually be to treat leukocyte signatures as a complementary risk/host component and, if feasible, add a cfDNA methylation layer for direct tumor signal and localization.

### Is 30x Buffy-Coat enough?

A 30× whole‑genome–equivalent depth on **buffy‑coat DNA** is generally *more than enough* for accurate methylation quantification at the CpG level, but it does not by itself solve the main limitation: buffy coat captures **host leukocyte methylation**, not tumor‑derived DNA. [pmc.ncbi.nlm.nih](https://pmc.ncbi.nlm.nih.gov/articles/PMC10262593/)

### What 30× gives you (buffy coat)

- Studies of WBC/buffy‑coat methylation usually consider much lower effective depths sufficient once reads are aggregated per CpG; targeted bisulfite amplicon work suggests 1,000× per CpG is ample, which corresponds to far less than 30× WGS depth after averaging across reads. [pmc.ncbi.nlm.nih](https://pmc.ncbi.nlm.nih.gov/articles/PMC10825794/)
- Population studies have successfully derived cancer‑risk and disease‑state signatures from buffy‑coat methylation (e.g., breast‑cancer risk, pregnancy, other conditions), indicating that leukocyte methylation carries detectable disease‑associated signals. [frontiersin](https://www.frontiersin.org/journals/bioengineering-and-biotechnology/articles/10.3389/fbioe.2021.782843/full)
- At 30× with EPIC‑style coverage, your technical noise is likely dominated by biology (cell‑type composition, inter‑individual variance) rather than read depth, so increasing depth further would give diminishing returns for detection performance.

### Where buffy coat still falls short vs cfDNA

- The main constraint is **biological specificity**, not coverage: leukocyte methylation reflects systemic inflammation, aging, and exposures, and only indirectly correlates with cancer, so signatures can be weaker and less tumor‑specific than cfDNA‑based assays that track circulating tumor DNA. [sciencedirect](https://www.sciencedirect.com/science/article/pii/S153561082200513X)
- For early detection and tumor localization, cfDNA methylation and fragmentomics clearly outperform leukocyte‑only approaches in multi‑cancer settings. [pnas](https://www.pnas.org/doi/10.1073/pnas.2209852119)

### Practical answer for your setting

- For a **prostate‑cancer classifier based purely on buffy‑coat methylation**, 30× depth is technically adequate; your gains now will mostly come from feature selection (e.g., focusing on robust leukocyte risk/host markers) and cell‑type deconvolution rather than more sequencing. [pmc.ncbi.nlm.nih](https://pmc.ncbi.nlm.nih.gov/articles/PMC10262593/)
- If your goal is to approach state‑of‑the‑art **early detection/MCED performance**, buffy coat alone will likely not be enough, regardless of depth; integrating cfDNA methylation (even at lower depth) would provide a qualitatively different and more tumor‑specific signal. [academic.oup](https://academic.oup.com/clinchem/article/70/11/1355/7744959)

Would you be open to a design where buffy coat provides a host‑risk score and cfDNA adds a tumor‑burden/tissue‑of‑origin layer, or do you need to stay strictly with buffy‑coat material for logistical reasons?
