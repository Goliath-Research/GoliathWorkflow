import {
  BarChart,
  Callout,
  Card,
  CardBody,
  CardHeader,
  CollapsibleSection,
  Divider,
  Grid,
  H1,
  H2,
  H3,
  LineChart,
  Pill,
  Row,
  Stack,
  Stat,
  Table,
  Text,
  useCanvasState,
} from "cursor/canvas";

const VERDICT = "NOT FREEZE READY";
const COHORT = "93 healthy vs 134 PCa (buffy-coat WGBS, CG)";
const SOURCE = "H_PCa_good/monte_carlo_runs · 20 iterations · seed 42";

const HEADLINE = {
  meanGeneBa: 0.618,
  bestGeneBa: 0.718,
  bestRun: "run_0016",
  meanDmpBa: 0.901,
  gap: 0.283,
  stableGenes: 0,
  stableDmps: 3824,
  runsPass09: 0,
  runsTotal: 20,
  meanSpecificity: 0.319,
};

const RUN_LABELS = Array.from({ length: 20 }, (_, i) => `R${String(i + 1).padStart(2, "0")}`);

const GENE_BA = [
  0.662, 0.615, 0.608, 0.581, 0.601, 0.588, 0.622, 0.595, 0.574, 0.689,
  0.613, 0.634, 0.615, 0.621, 0.61, 0.718, 0.599, 0.573, 0.57, 0.666,
];

const DMP_BA = Array(20).fill(0.901);

const SPECIFICITY = [
  0.324, 0.23, 0.216, 0.162, 0.203, 0.176, 0.243, 0.189, 0.149, 0.378,
  0.263, 0.526, 0.526, 0.316, 0.368, 0.474, 0.421, 0.368, 0.474, 0.368,
];

const SELECTED_K = [
  50, 50, 50, 50, 50, 50, 50, 50, 50, 50,
  18, 12, 15, 14, 16, 8, 11, 9, 7, 22,
];

const ISSUES = [
  {
    severity: "danger" as const,
    title: "Gene panel never reaches 0.9 BA target",
    detail: "Best run BA=0.718 (run_0016); 0/20 runs pass stability gate.",
  },
  {
    severity: "danger" as const,
    title: "Zero stable genes at 70% recurrence",
    detail: "Only 5/20 runs counted; 15 skipped for BA<0.9. Max gene freq=60% (MSH3).",
  },
  {
    severity: "warning" as const,
    title: "Healthy specificity collapse",
    detail: "Mean validation specificity=0.32 — ECDF gene layer over-predicts PCa (sensitivity ~1.0).",
  },
  {
    severity: "warning" as const,
    title: "Large DMP→gene performance gap",
    detail: "DMP-level BA ~0.90 vs gene-level ~0.62. Problem is aggregation/backend, not detection.",
  },
];

const CURRENT_PARAMS = [
  ["train_fraction", "0.8"],
  ["model_backend", "ecdf"],
  ["feature_mode", "raw_gene"],
  ["stability_min_balanced_accuracy", "0.9"],
  ["stability_target_balanced_accuracy", "0.9"],
  ["stability_min_selected_genes", "50"],
  ["stability_gene_featurecuts_max_genes", "500"],
  ["stability_gene_freq", "0.7"],
  ["stability_mapper_enrich_disease", "false"],
];

const TUNING = [
  {
    priority: 1,
    action: "Fix healthy-class collapse in gene ECDF layer",
    try: "min_selected_genes 50→20-30; max_genes 500→150-250",
  },
  {
    priority: 2,
    action: "Try tabular_sklearn with class_weight=balanced_subsample",
    try: "model_backend: ecdf → tabular_sklearn",
  },
  {
    priority: 3,
    action: "Relax stability BA gate for feasibility iteration",
    try: "stability_min_balanced_accuracy: 0.9 → 0.75",
  },
  {
    priority: 4,
    action: "Increase validation healthy sample count",
    try: "train_fraction: 0.8 → 0.7 (~28 healthy in val vs ~19)",
  },
  {
    priority: 5,
    action: "Align biomarker filter with mapper enrichment",
    try: "stability_mapper_enrich_disease: false → true",
  },
];

const TOP_GENES = [
  ["MSH3", "60%", "3/5"],
  ["ENSG00000305893", "60%", "3/5"],
  ["RNU1-151P", "60%", "3/5"],
  ["SUGT1P3", "40%", "2/5"],
  ["DMD", "40%", "2/5"],
  ["MTCO1P2", "40%", "2/5"],
];

const PER_RUN_ROWS = RUN_LABELS.map((_, i) => [
  `run_${String(i + 1).padStart(4, "0")}`,
  i < 10 ? "feature" : "quality",
  GENE_BA[i].toFixed(3),
  DMP_BA[i].toFixed(3),
  SPECIFICITY[i].toFixed(3),
  String(SELECTED_K[i]),
]);

const SECTIONS = [
  { id: "overview", label: "Overview" },
  { id: "performance", label: "Performance" },
  { id: "diagnosis", label: "Diagnosis" },
  { id: "tuning", label: "Tuning" },
  { id: "genes", label: "Gene stability" },
];

function SectionNav({
  active,
  onSelect,
}: {
  active: string;
  onSelect: (id: string) => void;
}) {
  return (
    <Row gap={8} wrap>
      {SECTIONS.map((s) => (
        <Pill key={s.id} active={active === s.id} onClick={() => onSelect(s.id)}>
          {s.label}
        </Pill>
      ))}
    </Row>
  );
}

export default function HPcaGoodMcAnalysis() {
  const [section, setSection] = useCanvasState("section", "overview");

  return (
    <Stack gap={24} style={{ padding: 24, maxWidth: 980 }}>
      <Stack gap={8}>
        <H1>H_PCa_good MC — Performance Analysis</H1>
        <Text tone="secondary">{COHORT}</Text>
        <Text tone="secondary" size="small">{SOURCE}</Text>
        <SectionNav active={section} onSelect={setSection} />
      </Stack>

      {section === "overview" && (
        <Stack gap={20}>
          <Callout tone="danger" title={VERDICT}>
            Gene-level validation balanced accuracy never reached the 0.9 stability gate.
            Zero stable genes at 70% recurrence across 20 completed MC iterations.
            Freeze readiness check returned ready=false.
          </Callout>

          <Grid columns={4} gap={12}>
            <Stat label="Mean gene BA" value={HEADLINE.meanGeneBa.toFixed(3)} tone="danger" />
            <Stat label="Best gene BA" value={`${HEADLINE.bestGeneBa.toFixed(3)}`} tone="warning" />
            <Stat label="Mean DMP BA" value={HEADLINE.meanDmpBa.toFixed(3)} tone="success" />
            <Stat label="DMP→gene gap" value={HEADLINE.gap.toFixed(3)} tone="danger" />
          </Grid>

          <Grid columns={4} gap={12}>
            <Stat label="Runs passing BA≥0.9" value={`${HEADLINE.runsPass09}/${HEADLINE.runsTotal}`} tone="danger" />
            <Stat label="Stable genes @70%" value={String(HEADLINE.stableGenes)} tone="danger" />
            <Stat label="Stable DMPs @80%" value={HEADLINE.stableDmps.toLocaleString()} />
            <Stat label="Mean healthy specificity" value={HEADLINE.meanSpecificity.toFixed(3)} tone="warning" />
          </Grid>

          <Card>
            <CardHeader>Key finding</CardHeader>
            <CardBody>
              <Text tone="secondary" size="small">
                Per-chromosome DMP classifier panels average ~90% balanced accuracy, but the
                ECDF raw_gene backend collapses healthy specificity to ~32%. The model achieves
                near-perfect PCa sensitivity at the cost of misclassifying most healthy validation
                samples. Stability analysis only counts 5 runs (those nearest the gate), yielding
                19 unique genes with none at ≥70% frequency. Best run: {HEADLINE.bestRun} (BA {HEADLINE.bestGeneBa.toFixed(3)}).
              </Text>
            </CardBody>
          </Card>
        </Stack>
      )}

      {section === "performance" && (
        <Stack gap={20}>
          <H2>Per-run validation metrics</H2>

          <Card>
            <CardHeader>Gene balanced accuracy by MC run</CardHeader>
            <CardBody>
              <BarChart
                categories={RUN_LABELS}
                series={[{ name: "Gene BA (validation)", data: GENE_BA, tone: "danger" }]}
                height={220}
                beginAtZero={false}
                yMin={0.5}
                yMax={1.0}
                referenceLines={[
                  { value: 0.9, label: "Stability gate (0.9)", tone: "warning" },
                  { value: HEADLINE.meanGeneBa, label: "Mean (0.618)", tone: "info" },
                ]}
              />
              <Text tone="secondary" size="small" style={{ marginTop: 8 }}>
                Source: gene_featurecuts_metrics.json · validation holdout · 20 MC runs ·
                feature (R01–R10) + quality (R11–R20)
              </Text>
            </CardBody>
          </Card>

          <Grid columns={2} gap={16}>
            <Card>
              <CardHeader>DMP vs gene BA</CardHeader>
              <CardBody>
                <LineChart
                  categories={RUN_LABELS}
                  series={[
                    { name: "DMP BA (mean/chr)", data: DMP_BA, tone: "success" },
                    { name: "Gene BA (validation)", data: GENE_BA, tone: "danger" },
                  ]}
                  height={200}
                  beginAtZero={false}
                  yMin={0.5}
                  yMax={1.0}
                  referenceLines={[{ value: 0.9, label: "Gate", tone: "warning" }]}
                />
                <Text tone="secondary" size="small" style={{ marginTop: 8 }}>
                  Source: dmp-export-*.meta.json vs gene_featurecuts_metrics.json
                </Text>
              </CardBody>
            </Card>

            <Card>
              <CardHeader>Healthy specificity by run</CardHeader>
              <CardBody>
                <BarChart
                  categories={RUN_LABELS}
                  series={[{ name: "Specificity (healthy class)", data: SPECIFICITY, tone: "warning" }]}
                  height={200}
                  beginAtZero
                  yMax={1.0}
                  referenceLines={[{ value: 0.5, label: "Random (0.5)", tone: "info" }]}
                />
                <Text tone="secondary" size="small" style={{ marginTop: 8 }}>
                  Source: validation_metrics.specificity · axis: specificity (0–1)
                </Text>
              </CardBody>
            </Card>
          </Grid>

          <CollapsibleSection title="Full per-run table (20 runs)" defaultOpen={false}>
            <Table
              headers={["Run", "Phase", "Gene BA", "DMP BA", "Specificity", "Selected k"]}
              rows={PER_RUN_ROWS}
              framed
            />
          </CollapsibleSection>
        </Stack>
      )}

      {section === "diagnosis" && (
        <Stack gap={20}>
          <H2>Issue diagnosis</H2>
          {ISSUES.map((issue) => (
            <Callout key={issue.title} tone={issue.severity} title={issue.title}>
              {issue.detail}
            </Callout>
          ))}

          <Card>
            <CardHeader>Confusion pattern (typical run, run_0010)</CardHeader>
            <CardBody>
              <Grid columns={2} gap={16}>
                <Stack gap={4}>
                  <H3>Validation confusion matrix</H3>
                  <Table
                    headers={["Actual \\ Predicted", "Healthy", "PCa"]}
                    rows={[
                      ["Healthy (74)", "28", "46"],
                      ["PCa (107)", "0", "107"],
                    ]}
                    framed
                  />
                </Stack>
                <Stack gap={4}>
                  <H3>Interpretation</H3>
                  <Text tone="secondary" size="small">
                    46 of 74 healthy samples misclassified as PCa (specificity 0.38).
                    All 107 PCa samples correctly identified (sensitivity 1.0).
                    Accuracy appears acceptable (0.75) but balanced accuracy is only 0.69
                    because the model defaults to the majority/disease class.
                  </Text>
                </Stack>
              </Grid>
            </CardBody>
          </Card>

          <Card>
            <CardHeader>Current MC parameters</CardHeader>
            <CardBody>
              <Table headers={["Parameter", "Current value"]} rows={CURRENT_PARAMS} framed />
              <Text tone="secondary" size="small" style={{ marginTop: 8 }}>
                Source: monte_carlo_runs/queue/mc_config.json
              </Text>
            </CardBody>
          </Card>
        </Stack>
      )}

      {section === "tuning" && (
        <Stack gap={20}>
          <H2>Recommended parameter changes</H2>
          <Text tone="secondary" size="small">
            Ordered by expected impact. Re-run MC after changes; compare against this baseline
            (mean gene BA 0.618, best 0.718).
          </Text>

          {TUNING.map((rec) => (
            <Card key={rec.priority}>
              <CardHeader>{`${rec.priority}. ${rec.action}`}</CardHeader>
              <CardBody>
                <Text weight="semibold">Try: {rec.try}</Text>
              </CardBody>
            </Card>
          ))}

          <Divider />

          <Callout tone="info" title="Suggested next experiment profile">
            Start with a single change set: min_selected_genes=25, max_genes=200,
            stability_min_balanced_accuracy=0.75, model_backend=tabular_sklearn.
            If gene BA improves above 0.75, tighten gates incrementally.
          </Callout>
        </Stack>
      )}

      {section === "genes" && (
        <Stack gap={20}>
          <H2>Gene stability (5 runs counted)</H2>
          <Callout tone="warning" title="No genes meet 70% recurrence threshold">
            Stability counted only runs with gene BA nearest the 0.9 gate. Of 19 unique genes,
            the highest recurrence is 60% (3/5 runs). Many appear to be mitochondrial/pseudogene
            loci rather than recurrent biological signal.
          </Callout>

          <Card>
            <CardHeader>Top genes by MC recurrence</CardHeader>
            <CardBody>
              <Table headers={["Gene", "Frequency", "Count"]} rows={TOP_GENES} framed />
              <Text tone="secondary" size="small" style={{ marginTop: 8 }}>
                Source: monte_carlo_runs/stability/gene_frequency.csv · min_freq threshold 0.7
              </Text>
            </CardBody>
          </Card>

          <Card>
            <CardHeader>Selected k vs gene BA</CardHeader>
            <CardBody>
              <BarChart
                categories={RUN_LABELS}
                series={[{ name: "FeatureCuts selected k", data: SELECTED_K, tone: "info" }]}
                height={180}
                referenceLines={[{ value: 50, label: "min_selected_genes (50)", tone: "warning" }]}
              />
              <Text tone="secondary" size="small" style={{ marginTop: 8 }}>
                Best BA (run_0016, 0.718) used k=8 — well below forced minimum of 50 on feature phase.
                Source: gene_featurecuts_metrics.json selected_k
              </Text>
            </CardBody>
          </Card>
        </Stack>
      )}

      <Divider />
      <Text tone="secondary" size="small">
        Artifacts: /work/projects/prostate-cancer/H_PCa_good/mc_analysis/h_pca_good_mc_analysis.json
      </Text>
    </Stack>
  );
}
