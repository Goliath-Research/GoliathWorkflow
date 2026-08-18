import {
  Callout,
  Card,
  CardBody,
  CardHeader,
  Code,
  Divider,
  Grid,
  H1,
  H2,
  Pill,
  Row,
  Stack,
  Stat,
  Table,
  Text,
  useCanvasState,
} from "cursor/canvas";

const LEAKAGE = [
  ["Houseman / HiTIMED Ω", "Yes — no disease label", "May run once on the cohort"],
  ["Smoking / clock / BMI / CRP scores", "Yes — label-free weighted betas", "May run once on the cohort"],
  ["OLS M ~ Z coefficients", "No", "Train IDs of that split only; no Group term"],
  ["Apply β_adj", "Frozen γ̂ on train and held-out", "Never re-fit on held-out or a new sample"],
  ["Monte Carlo", "Repeat fit inside every iteration", "Do not residualize full cohort then split"],
  ["Production sample", "Independent scores + freeze coefficients", "Never re-fit OLS on the incoming sample"],
];

const ISOLATION = [
  ["Methylation / RNA / proteomics process packs", "Untouched"],
  ["buffy_wgbs_pangenome_gene_fc", "Untouched — default unadjusted DMP path"],
  ["mc_stability / study_validation_lifecycle", "Forks only (*_residual)"],
  ["pipeline.centroid / classifier", "Opt-in iff residualizeCoefDir is bound"],
  ["New scores + residualize_fit actions", "Catalog add; shipped programs never call them"],
  ["primary_analyte: buffy_coat", "Does not auto-enable residualization"],
];

const PANELS = [
  ["Smoking", "smoking_ahr_v1.json", "AHRR cg05575921 + small Joehanes/Zeilinger set"],
  ["Epigenetic age", "horvath2013_stub_v1.json", "Stub — replace with a full clock asset"],
  ["BMI / adiposity", "bmi_adiposity_v1.json", "HIF3A, ABCG1, CPT1A and related sites"],
  ["Inflammation / CRP", "crp_inflammation_v1.json", "Small Wielscher/Ligthart-derived set"],
];

const SECTIONS = [
  { id: "isolation", label: "Isolation" },
  { id: "leakage", label: "Leakage" },
  { id: "math", label: "M-values" },
  { id: "topology", label: "Topology" },
  { id: "caveat", label: "Ω caveat" },
];

export default function BuffyMvalueResidualizationCanvas() {
  const [section, setSection] = useCanvasState("section", "isolation");

  return (
    <Stack gap={24} style={{ padding: 24, maxWidth: 980 }}>
      <Stack gap={8}>
        <H1>Buffy M-value residualization</H1>
        <Text tone="secondary">
          Opt-in assay procedure for confounder-aware DMP calling. Still DNA methylation WGBS —
          not a new omics process pack. gene_importance formula is unchanged.
        </Text>
        <Row gap={8} wrap>
          <Pill tone="info">buffy_wgbs_mvalue_residual_gene_fc</Pill>
          <Pill tone="neutral">procedure + program fork</Pill>
          <Pill tone="warning">Shipped packs unchanged</Pill>
        </Row>
      </Stack>

      <Grid columns={3} gap={12}>
        <Stat value="Train-only" label="OLS fit per MC split" />
        <Stat value="(0, 1)" label="β_adj after inverse logit" />
        <Stat value="Unchanged" label="gene_importance formula" />
      </Grid>

      <Row gap={8} wrap>
        {SECTIONS.map((s) => (
          <Pill key={s.id} active={section === s.id} onClick={() => setSection(s.id)}>
            {s.label}
          </Pill>
        ))}
      </Row>

      {section === "isolation" && (
        <Stack gap={16}>
          <Callout tone="warning" title="Why a new pack">
            Residualization rewrites the betas that centroids, DMPs, and gene_importance see.
            Gating nodes onto the production lifecycle would risk a profile merge turning it on
            for every buffy, cfDNA, plant, RNA, and proteomics study.
          </Callout>
          <Table
            headers={["Shipped artifact", "Rule"]}
            rows={ISOLATION}
            rowTone={["success", "success", "info", "info", "neutral", "success"]}
          />
          <Text size="small" tone="secondary">
            Source: docs/research/buffy-mvalue-residualization.md
          </Text>
        </Stack>
      )}

      {section === "leakage" && (
        <Stack gap={16}>
          <H2>What may see the full cohort</H2>
          <Table headers={["Quantity", "All samples?", "Constraint"]} rows={LEAKAGE} />
          <Callout tone="info" title="Constant covariates">
            All-never-smoker (or otherwise near-zero-variance) columns are dropped before OLS so
            they cannot numerically explode. Threshold is actionConfig.residualize.variance_threshold.
          </Callout>
        </Stack>
      )}

      {section === "math" && (
        <Stack gap={16}>
          <H2>Locked transform</H2>
          <Card>
            <CardHeader>M-value round-trip</CardHeader>
            <CardBody>
              <Stack gap={8}>
                <Text>
                  Clip β to [ε, 1−ε], then M = log2(β / (1−β)). Residualize M on train-only Z.
                  Inverse: β_adj = 2^M_res / (1 + 2^M_res), clipped to (0, 1).
                </Text>
                <Text tone="secondary" size="small">
                  β_adj is an adjusted signal forced back into (0, 1), not a methylation
                  proportion. Sm/Su stay raw; only Sx, Sx2, and histogram bins use β_adj.
                </Text>
                <Code>methyl_utils.mvalue_residualize</Code>
              </Stack>
            </CardBody>
          </Card>
          <Table headers={["Score", "Packaged panel", "Honesty"]} rows={PANELS} />
        </Stack>
      )}

      {section === "topology" && (
        <Stack gap={16}>
          <H2>Residual fork vs shipped lifecycle</H2>
          <Grid columns={2} gap={16}>
            <Card>
              <CardHeader>Today (unchanged)</CardHeader>
              <CardBody>
                <Text size="small">
                  MC: centroid then detector on raw beta. Freeze mapper, then deconv for the ECDF
                  second-stage ALR stack. Composition-mediated DMPs remain in gene_importance.
                </Text>
              </CardBody>
            </Card>
            <Card>
              <CardHeader>Residual programs</CardHeader>
              <CardBody>
                <Text size="small">
                  Once: deconv + methylation scores. Per split: OLS on train M-values, apply frozen
                  coefs, centroid Sx from β_adj, detector/mapper unchanged. Freeze persists
                  coefficients under production/residualize/.
                </Text>
              </CardBody>
            </Card>
          </Grid>
          <Text size="small" tone="secondary">
            Programs: mc_stability_residual.program.json,
            study_validation_lifecycle_residual.program.json. Sensitivity CLI:
            methyl-residualize-sensitivity.
          </Text>
        </Stack>
      )}

      {section === "caveat" && (
        <Stack gap={16}>
          <Callout tone="danger" title="Ω can remove cancer signal">
            If cancer → inflammation → Ω → methylation, residualizing Ω removes part of the buffy
            cancer signal from the DMP list. Procedure default still includes Ω. Operators who want
            composition-mediated DMPs omit composition_columns and keep today’s ALR second-stage.
          </Callout>
          <Divider />
          <Text>
            gene_importance stays effect_size × frequency × bio_weight. After residualization it
            means confounder-adjusted host-response, not leukocyte mix. Do not invent a second
            importance formula.
          </Text>
        </Stack>
      )}
    </Stack>
  );
}
