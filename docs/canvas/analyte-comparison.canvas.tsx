import {
  BarChart,
  Callout,
  Card,
  CardBody,
  CardHeader,
  Code,
  CollapsibleSection,
  Divider,
  Grid,
  H1,
  H2,
  H3,
  Pill,
  Row,
  Stack,
  Stat,
  Table,
  Text,
  useCanvasState,
} from "cursor/canvas";

const SHARED_RECURRENT_GENES = [
  "DLGAP2",
  "GSE1",
  "NCOR2",
  "PTPRN2",
  "RBFOX3",
  "SORCS2",
];

const MC_OVERLAP_BY_RUN = [
  { run: "run_0001", jaccard: 0.149, shared: 13 },
  { run: "run_0002", jaccard: 0.124, shared: 11 },
  { run: "run_0003", jaccard: 0.149, shared: 13 },
  { run: "run_0004", jaccard: 0.266, shared: 21 },
  { run: "run_0005", jaccard: 0.299, shared: 23 },
  { run: "run_0006", jaccard: 0.111, shared: 10 },
  { run: "run_0007", jaccard: 0.176, shared: 15 },
  { run: "run_0008", jaccard: 0.316, shared: 24 },
  { run: "run_0009", jaccard: 0.124, shared: 11 },
  { run: "run_0010", jaccard: 0.163, shared: 14 },
];

const RUBRIC_AXES = [
  { axis: "MC gene recurrence", weight: "High", buffy: "39 genes @ ≥70%", plasma: "32 genes @ ≥70%" },
  { axis: "Cross-analyte gene concordance", weight: "High", buffy: "15.4% panel shared", plasma: "18.8% panel shared" },
  { axis: "Discovery mapper gene Jaccard", weight: "Medium", buffy: "—", plasma: "0.81 (shared)" },
  { axis: "Discovery DMP direction", weight: "Medium", buffy: "—", plasma: "83% on shared loci" },
  { axis: "MC mapper signature", weight: "Medium", buffy: "10/10 buffy-dominant", plasma: "10/10 buffy-dominant" },
  { axis: "Technical QC", weight: "Medium", buffy: "30 eligible, 24/24 H5", plasma: "30 eligible + fragmentomics" },
  { axis: "Production frozen genes", weight: "Low", buffy: "21 genes", plasma: "32 genes" },
  { axis: "Post-model ECE (mean)", weight: "Low", buffy: "0.00078", plasma: "0.00256" },
];

const SECTIONS = [
  { id: "overview", label: "Overview" },
  { id: "mc-genes", label: "MC gene panels" },
  { id: "discovery", label: "Discovery biology" },
  { id: "qc", label: "QC" },
  { id: "production", label: "Production freeze" },
  { id: "pathways", label: "Pathways" },
  { id: "recommendation", label: "Recommendation" },
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

export default function AnalyteComparisonCanvas() {
  const [section, setSection] = useCanvasState("section", "overview");

  return (
    <Stack gap={24} style={{ padding: 24, maxWidth: 980 }}>
      <Stack gap={8}>
        <H1>Plasma vs Buffy-coat analyte comparison</H1>
        <Text tone="secondary">
          Paired prostate-cancer feasibility study (n=15 healthy + 15 PCa per analyte, 30 paired
          subjects). Both analytes ran the <Code>mc_gene_fc</Code> profile with 10 MC iterations.
        </Text>
        <Row gap={8}>
          <Pill tone="info">mc_gene_fc</Pill>
          <Pill tone="neutral">all/PCa</Pill>
          <Pill tone="warning">Feasibility only — small N</Pill>
        </Row>
      </Stack>

      <SectionNav active={section} onSelect={setSection} />

      {section === "overview" && (
        <Stack gap={16}>
          <Callout tone="warning" title="Interpretation constraints">
            MC validation balanced accuracy ≈ 1.0 at n≈15/arm is not decision-grade. Classifier-axis
            stability aggregation skipped all runs (empty stable_*_production.csv). Primary evidence:
            per-run gene FeatureCuts panels and gene_frequency.csv.
          </Callout>

          <Card>
            <CardHeader>Study design</CardHeader>
            <CardBody>
              <Grid columns={2} gap={16}>
                <Stack gap={8}>
                  <Text weight="semibold">Cohort</Text>
                  <Text tone="secondary" size="small">
                    30 paired subjects with plasma (cfDNA) and buffy-coat WGBS from the same patient.
                    Pairing manifest:{" "}
                    <Code>/work/projects/prostate-cancer/data/plasma_buffy_pairing.csv</Code>
                  </Text>
                </Stack>
                <Stack gap={8}>
                  <Text weight="semibold">Pipeline</Text>
                  <Text tone="secondary" size="small">
                    10 MC runs per analyte, gene FeatureCuts (ECDF backend), comparison all/PCa.
                    Output root:{" "}
                    <Code>/work/projects/prostate-cancer/analyte_comparison/</Code>
                  </Text>
                </Stack>
              </Grid>
            </CardBody>
          </Card>

          <Grid columns={3} gap={12}>
            <Stat value="3.341" label="Buffy weighted score" tone="success" />
            <Stat value="3.338" label="Plasma weighted score" />
            <Stat value="6" label="Shared recurrent genes (≥70%)" />
          </Grid>
        </Stack>
      )}

      {section === "mc-genes" && (
        <Stack gap={16}>
          <H2>MC gene FeatureCuts panels</H2>
          <Text tone="secondary" size="small">
            Source: mc_gene_fc/ · 50 genes selected per run per analyte · Jun 2026 cluster run
          </Text>

          <Grid columns={3} gap={12}>
            <Stat value="39" label="Buffy recurrent genes (freq ≥ 0.7)" />
            <Stat value="32" label="Plasma recurrent genes (freq ≥ 0.7)" />
            <Stat value="0.09" label="Recurrent-panel Jaccard" />
          </Grid>

          <Card>
            <CardHeader>Per-run 50-gene panel Jaccard (plasma vs buffy)</CardHeader>
            <CardBody>
              <BarChart
                categories={MC_OVERLAP_BY_RUN.map((r) => r.run)}
                series={[
                  {
                    name: "Jaccard index",
                    data: MC_OVERLAP_BY_RUN.map((r) => r.jaccard),
                  },
                ]}
                height={220}
                valueSuffix=""
                beginAtZero
                yMax={0.35}
                referenceLines={[{ value: 0.2, label: "mean ~0.19" }]}
              />
              <Text tone="secondary" size="small" style={{ marginTop: 8 }}>
                Y-axis: Jaccard index (0–1). X-axis: MC run ID. Each bar compares the 50-gene
                classifier panel from the same MC iteration across analytes.
              </Text>
            </CardBody>
          </Card>

          <Card>
            <CardHeader trailing={<Text tone="secondary" size="small">6 genes</Text>}>
              Shared recurrent genes (frequency ≥ 0.7 in both analytes)
            </CardHeader>
            <CardBody>
              <Row gap={8} wrap>
                {SHARED_RECURRENT_GENES.map((g) => (
                  <Pill key={g}>{g}</Pill>
                ))}
              </Row>
            </CardBody>
          </Card>

          <Callout tone="info" title="Run coverage">
            Buffy gene_frequency table includes all 10/10 MC runs. Plasma top-tier frequency counts
            reflect 8/10 runs — slightly lower panel stability under resampling.
          </Callout>
        </Stack>
      )}

      {section === "discovery" && (
        <Stack gap={16}>
          <H2>Discovery biology overlap</H2>
          <Text tone="secondary" size="small">
            Source: all_vs_PCa/discovery/ · genome-wide mapper and DMP comparison
          </Text>

          <Grid columns={3} gap={12}>
            <Stat value="0.81" label="Mapper gene Jaccard" tone="success" />
            <Stat value="0.07" label="Discovery DMP Jaccard" />
            <Stat value="83%" label="Direction concordance (shared DMPs)" />
          </Grid>

          <Card>
            <CardHeader>Discovery vs classifier DMP overlap</CardHeader>
            <CardBody>
              <Table
                headers={["Layer", "DMP Jaccard", "Direction concordance", "Interpretation"]}
                rows={[
                  [
                    "Discovery",
                    "0.068",
                    "83%",
                    "Analyte-specific loci; shared loci agree on direction",
                  ],
                  [
                    "Classifier",
                    "0.008",
                    "67%",
                    "Post-selection panels diverge strongly",
                  ],
                ]}
                framed
              />
            </CardBody>
          </Card>

          <Text tone="secondary" size="small">
            Gene-level mapper overlap is high (~81% Jaccard) while locus-level DMP overlap is low —
            consistent with shared gene programs but analyte-specific methylation sites.
          </Text>
        </Stack>
      )}

      {section === "qc" && (
        <Stack gap={16}>
          <H2>Sample QC and alignment</H2>
          <Text tone="secondary" size="small">Source: qc/summary.json · sample_qc reports</Text>

          <Table
            headers={["Metric", "Buffy-coat", "Plasma (cfDNA)"]}
            rows={[
              ["Eligible samples", "30 / 30", "30 / 30"],
              ["H5 coverage per sample", "24 / 24", "24 / 24"],
              ["Fragmentomics", "N/A", "Present (production bundle)"],
              ["Paired subjects", "30", "30 (same patients)"],
            ]}
            framed
          />

          <Callout tone="neutral" title="QC parity">
            Both analytes pass sample eligibility gates with full expected H5 coverage. Plasma adds
            cfDNA fragmentomics under production/fragmentomics for assay-specific QC.
          </Callout>
        </Stack>
      )}

      {section === "production" && (
        <Stack gap={16}>
          <H2>Production freeze bundles</H2>
          <Text tone="secondary" size="small">
            Source: production/freeze_overlap.json · Jun 2026 freeze (predates latest full MC pass)
          </Text>

          <Grid columns={2} gap={12}>
            <Stat value="21" label="Buffy frozen genes" />
            <Stat value="32" label="Plasma frozen genes" />
          </Grid>

          <Card>
            <CardHeader>Frozen panel overlap</CardHeader>
            <CardBody>
              <Table
                headers={["Artifact", "Buffy", "Plasma", "Shared", "Jaccard"]}
                rows={[
                  ["Frozen genes", "21", "32", "6", "0.13"],
                  ["Stable DMPs (genomewide)", "6,629", "11,452", "74", "0.004"],
                  ["Post-model ECE (mean)", "0.00078", "0.00256", "—", "buffy lower"],
                ]}
                framed
              />
              <Divider />
              <Text weight="semibold" size="small">
                Shared frozen genes (same six as MC recurrence)
              </Text>
              <Row gap={8} wrap style={{ marginTop: 8 }}>
                {SHARED_RECURRENT_GENES.map((g) => (
                  <Pill key={g}>{g}</Pill>
                ))}
              </Row>
            </CardBody>
          </Card>
        </Stack>
      )}

      {section === "pathways" && (
        <Stack gap={16}>
          <H2>Pathway / PPI signature recurrence</H2>
          <Text tone="secondary" size="small">
            Source: signature_recurrence/ · 25-gene plasma vs buffy hub signatures from discovery
            enricher
          </Text>

          <Callout tone="warning" title="Unexpected MC mapper pattern">
            On the plasma project, all 10 MC mapper contexts were buffy-signature-dominant (not
            plasma-dominant). Root discovery enricher PPI hubs on the plasma project were
            plasma-dominant (25/25 overlap). MC resampling may preserve buffy-coat hub biology in
            plasma mapper gene sets.
          </Callout>

          <Table
            headers={["Context", "Plasma project dominant", "Buffy project dominant"]}
            rows={[
              ["Discovery enricher PPI hubs", "Plasma (25/25)", "Buffy (expected)"],
              ["MC mapper (10 runs each)", "Buffy (10/10)", "Buffy (10/10)"],
            ]}
            framed
          />

          <CollapsibleSection title="Plasma signature genes (discovery hubs, n=25)" defaultOpen={false}>
            <Text size="small" tone="secondary">
              DMD, PCDH11X, IL1RAPL1, L1CAM, MECP2, STS, FLNA, DACH2, TBL1X, HCFC1, KDM6A, OPHN1,
              TENM1, GABRA3, BCOR, SH3KBP1, ARHGAP6, GPC3, HTR2C, PHEX, FGF13, STAG2, AR, ANOS1,
              CACNA1F
            </Text>
          </CollapsibleSection>
        </Stack>
      )}

      {section === "recommendation" && (
        <Stack gap={16}>
          <H2>Decision rubric</H2>
          <Callout tone="success" title="Lean: buffy-coat (marginal)">
            Weighted total 3.341 (buffy) vs 3.338 (plasma). Not a strong separation — use for assay
            development direction, not clinical performance claims.
          </Callout>

          <Card>
            <CardHeader>Weighted MC rubric scores</CardHeader>
            <CardBody>
              <BarChart
                categories={["MC recurrence", "Cross-analyte concordance", "Mean MC BA"]}
                series={[
                  { name: "Buffy-coat", data: [3.71, 1.62, 1.0] },
                  { name: "Plasma (cfDNA)", data: [3.66, 1.75, 0.983] },
                ]}
                height={200}
                beginAtZero
                yMax={4}
              />
              <Text tone="secondary" size="small" style={{ marginTop: 8 }}>
                Source: mc_gene_fc/mc_gene_decision_scores.json · Weights: recurrence 50%,
                concordance 30%, mean BA 20% (BA down-weighted for small N).
              </Text>
            </CardBody>
          </Card>

          <Card>
            <CardHeader>Full rubric axes</CardHeader>
            <CardBody>
              <Table
                headers={["Axis", "Weight", "Buffy-coat", "Plasma"]}
                rows={RUBRIC_AXES.map((r) => [r.axis, r.weight, r.buffy, r.plasma])}
                framed
                stickyHeader
              />
            </CardBody>
          </Card>

          <Stack gap={8}>
            <H3>Buffy-coat advantages</H3>
            <Text tone="secondary" size="small">
              Higher recurrent gene count under MC (39 vs 32); all 10 runs contribute to gene
              frequency; marginally higher weighted score; lower post-model ECE.
            </Text>
            <H3>Plasma advantages</H3>
            <Text tone="secondary" size="small">
              Larger discovery/production DMP burden; larger production frozen gene panel (32 vs 21);
              discovery enricher PPI hubs match plasma signature; fragmentomics QC available.
            </Text>
            <H3>Shared biology</H3>
            <Text tone="secondary" size="small">
              Six-gene recurrent core (DLGAP2, GSE1, NCOR2, PTPRN2, RBFOX3, SORCS2); discovery
              mapper gene Jaccard 0.81; 83% direction concordance on shared discovery DMP loci.
            </Text>
          </Stack>

          <Text tone="secondary" size="small">
            On-disk report:{" "}
            <Code>/work/projects/prostate-cancer/analyte_comparison/README.md</Code> ·{" "}
            <Code>decision_scores.json</Code>
          </Text>
        </Stack>
      )}
    </Stack>
  );
}
