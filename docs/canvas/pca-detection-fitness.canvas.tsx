import {
  Callout,
  Card,
  CardBody,
  CardHeader,
  CollapsibleSection,
  Divider,
  Grid,
  H1,
  H2,
  Pill,
  Row,
  Select,
  Stack,
  Stat,
  Table,
  Text,
  useCanvasState,
} from "cursor/canvas";

type SectionId =
  | "verdict"
  | "assertions"
  | "feasibility"
  | "fitness"
  | "extensions"
  | "questions";

type FeasibilityFilter =
  | "all"
  | "already"
  | "config"
  | "small"
  | "large"
  | "reject";

const SECTIONS: { id: SectionId; label: string }[] = [
  { id: "verdict", label: "Verdict" },
  { id: "assertions", label: "Assertions" },
  { id: "feasibility", label: "Feasibility" },
  { id: "fitness", label: "Fitness gaps" },
  { id: "extensions", label: "Extensions" },
  { id: "questions", label: "Open questions" },
];

const ASSERTIONS = [
  {
    claim: "Gatekeeper NPV ≥95% for csPCa (GG≥2)",
    support: "Strong clinical consensus for rule-out tests; prevalence dependence noted",
    risk: "Clinical target, not current evidence; must not become a Python default",
    tone: "neutral" as const,
  },
  {
    claim: "Separate GG1 (3+3) from GG2 (3+4)",
    support: "Clinically sound transition point",
    risk: "Hard in liquid biopsy; Buffy healthy-vs-PCa does not test this",
    tone: "warning" as const,
  },
  {
    claim: "Estimate pattern-4 % burden",
    support: "Plausible utility; needs pathology validation",
    risk: "Speculative for cfDNA/urine methylation; continuous endpoint missing",
    tone: "warning" as const,
  },
  {
    claim: "Spatial localization for targeted biopsy",
    support: "High clinical value for imaging",
    risk: "Out of scope for blood/urine methylation software",
    tone: "danger" as const,
  },
  {
    claim: "Localized PCa → very low ctDNA; WGBS inefficient",
    support: "Well-supported literature consensus",
    risk: "Implies assay redesign (depth/targeting), not software knobs alone",
    tone: "neutral" as const,
  },
  {
    claim: "Buffy alone unlikely to grade-discriminate",
    support: "Aligns with BuffyCoat_vs_cfDNA research note",
    risk: "Current Buffy SaMD path is host-response, not gatekeeper biology",
    tone: "warning" as const,
  },
  {
    claim: "Buffy as matched hematopoietic control",
    support: "Sound for mutations; useful methylation confounding control",
    risk: "Needs paired study design; not automatic today",
    tone: "success" as const,
  },
  {
    claim: "Prefer targeted deep methylation (urine/cfDNA)",
    support: "Sound engineering for low tumor fraction",
    risk: "Wet-lab + CRO; pipeline still consumes FASTQ→BAM→H5",
    tone: "success" as const,
  },
  {
    claim: "Candidate genes (GSTP1, APC, RASSF1A, …)",
    support: "Reasonable literature candidates",
    risk: "Must stay study/profile priors — never Python hardcoding",
    tone: "warning" as const,
  },
  {
    claim: "EM-seq + hybrid capture @ 2–5k×",
    support: "Operationally plausible SOW",
    risk: "Outside MethylPipeline; chemistry is upstream",
    tone: "neutral" as const,
  },
  {
    claim: "GRAIL wide/shallow vs narrow/deep gatekeeper",
    support: "Directionally correct tradeoff",
    risk: "Some TF/Stage I numbers are marketing-grade speculation",
    tone: "warning" as const,
  },
  {
    claim: "Pan-cancer probe set + TOO hierarchical NN",
    support: "Wet-lab modularity OK",
    risk: "≠ current ECDF/FeatureCuts/MC stability architecture",
    tone: "danger" as const,
  },
];

const FEASIBILITY = [
  {
    rec: "NPV/PPV/sens/spec with CIs",
    bucket: "already" as const,
    detail: "clinical_performance.py, Wilson CIs, holdout Workflow 3",
  },
  {
    rec: "Gleason-staged disease stages in manifest",
    bucket: "config" as const,
    detail: "Study stages + SaMD staged program (usage ch.16)",
  },
  {
    rec: "SaMD ladder before clinical claims",
    bucket: "already" as const,
    detail: "samd_research → holdout → pivotal; claims blocked pre-pivotal",
  },
  {
    rec: "Buffy research with dual_fc",
    bucket: "already" as const,
    detail: "Buffy migrated to samd_research + dual_fc",
  },
  {
    rec: "Primary analyte cfDNA + fragmentomics",
    bucket: "config" as const,
    detail: "regulatory.primary_analyte: cfdna; SamplePrep fragmentomics",
  },
  {
    rec: "MC stability → freeze fixed_dmp_panel",
    bucket: "already" as const,
    detail: "Discovery path; capture BED compatible if sequenced",
  },
  {
    rec: "Positive class = csPCa GG≥2 for NPV",
    bucket: "small" as const,
    detail: "screening_binary is control_vs_pooled_disease today",
  },
  {
    rec: "min_npv_lcb + prevalence metadata",
    bucket: "small" as const,
    detail: "Only min_sensitivity_lcb / min_specificity_lcb exist",
  },
  {
    rec: "Rule-out operating-point selection",
    bucket: "small" as const,
    detail: "Metrics exist; threshold policy not first-class",
  },
  {
    rec: "Soft gene/region prior overlays",
    bucket: "small" as const,
    detail: "Profile/site actionConfig; no GSTP1 hardcoding",
  },
  {
    rec: "Paired plasma + buffy background",
    bucket: "config" as const,
    detail: "Study design; paired subtraction not a dedicated action",
  },
  {
    rec: "EM-seq / hybrid-capture SOW",
    bucket: "reject" as const,
    detail: "Out of pipeline — wet-lab/CRO",
  },
  {
    rec: "Pattern-4 % continuous model",
    bucket: "large" as const,
    detail: "New endpoint + labels + validation",
  },
  {
    rec: "Spatial lesion localization",
    bucket: "reject" as const,
    detail: "Imaging / other modality",
  },
  {
    rec: "Pan-cancer TOO hierarchical NN",
    bucket: "large" as const,
    detail: "Not current MethylPipeline architecture",
  },
  {
    rec: "New SQL NodeTypes for gatekeeper",
    bucket: "reject" as const,
    detail: "Architecture forbids; defer science to workers",
  },
];

const BUCKET_LABEL: Record<FeasibilityFilter, string> = {
  all: "All",
  already: "Already possible",
  config: "Config / ops",
  small: "Small code",
  large: "Large redesign",
  reject: "Reject / out of scope",
};

const BUCKET_PILL: Record<
  Exclude<FeasibilityFilter, "all">,
  "success" | "info" | "warning" | "deleted" | "neutral"
> = {
  already: "success",
  config: "info",
  small: "warning",
  large: "deleted",
  reject: "neutral",
};

const EXTENSIONS = [
  {
    rank: 1,
    title: "Configurable clinical screening roles",
    impact: "High",
    effort: "Small code",
    detail: "Positive = GG≥2; GG1 as control-side or separate class; report NPV for that definition",
  },
  {
    rank: 2,
    title: "min_npv_lcb + prevalence metadata",
    impact: "High",
    effort: "Small code",
    detail: "Validation schema + clinical_performance acceptance gates (config-not-code)",
  },
  {
    rank: 3,
    title: "Plasma/urine Gleason-staged SaMD study",
    impact: "High",
    effort: "Config + ops",
    detail: "samd_research + dual_fc with real locked_test partitions — data is the blocker",
  },
  {
    rank: 4,
    title: "Rule-out operating-point selection",
    impact: "Med–high",
    effort: "Small–medium",
    detail: "Threshold policy optimizing NPV/sensitivity under prevalence assumptions",
  },
  {
    rank: 5,
    title: "Soft region/gene prior overlays",
    impact: "Medium",
    effort: "Small–medium",
    detail: "BED or gene list via profile/site actionConfig — bias discovery without hardcoding",
  },
];

const GAPS = [
  "Wrong primary biology if claim is pre-biopsy csPCa rule-out (Buffy host-response ≠ gatekeeper)",
  "Wrong screening definition: pooled any-disease ≠ GG≥2 positive for NPV",
  "No NPV LCB / prevalence-conditioned acceptance in config schema",
  "No pattern-4 burden or spatial outputs",
  "Discovery assumes WGBS-style genome-wide H5; capture needs upstream + profile QC tweaks",
  "Live prostate evidence packages lack holdouts / pivotal partitions",
];

const FITS_TODAY = [
  "MC stability, FeatureCuts (dual_fc), enricher/PPI, freeze, locked model, PCCP",
  "Multi-stage Gleason cohorts + OVR-style backends",
  "Clinical performance reports with NPV; partitions; SaMD claim gating",
  "cfDNA path with fragmentomics + analyte-match guards",
  "Evidence index under docs/regulatory/",
];

const DO_NOT = [
  "Hardcode prostate genes, Gleason cutoffs, or NPV≥0.95 into DEFAULT_* / Pydantic defaults",
  "Create prostate-specific DomainPrograms or SQL NodeTypes",
  "Treat Buffy healthy-vs-PCa BA as gatekeeper clinical evidence",
  "Enable allow_clinical_performance_claims before samd_pivotal + pivotal_validation",
  "Bake GRAIL marketing numbers into acceptance criteria",
  "Implement spatial localization or pan-cancer TOO NN because the doc said so",
];

const QUESTIONS = [
  "Near-term intended use: buffy host-response, or pre-biopsy gatekeeper (plasma/urine + GG labels)?",
  "Pre-biopsy cohorts with GG1 vs GG≥2 and patient-disjoint holdouts — available or acquirable?",
  "Wet-lab: EM-seq + hybrid capture, or WGBS discovery then shrink panel?",
  "Pattern-4 % and spatial localization — in-scope SaMD claims or aspirational only?",
  "For NPV: does GG1 count as negative (defer biopsy) or a third category?",
];

function SectionNav({
  active,
  onSelect,
}: {
  active: SectionId;
  onSelect: (id: SectionId) => void;
}) {
  return (
    <Row gap={8} wrap>
      {SECTIONS.map((s) => (
        <Pill active={active === s.id} onClick={() => onSelect(s.id)}>
          {s.label}
        </Pill>
      ))}
    </Row>
  );
}

function VerdictSection() {
  return (
    <Stack gap={16}>
      <Callout tone="warning" title="Adopt with caveats">
        Gatekeeper framing and buffy-only / shallow-WGBS critique are sound. EM-seq SOW and
        pan-cancer hierarchical NN are wet-lab / future architecture — not “few pipeline
        changes.” Software/evidence half is feasible via SaMD ladder + staged cohorts + clinical
        metrics after analyte/endpoint redesign.
      </Callout>
      <Grid columns={3} gap={12}>
        <Stat value="Adopt*" label="Verdict (*with caveats)" tone="warning" />
        <Stat value="5" label="Priority extensions" />
        <Stat value="5" label="Open product questions" />
      </Grid>
      <Text tone="secondary" size="small">
        Source: docs/research/Prostate Cancer Detection.md · Analysis:
        docs/research/Prostate_Cancer_Detection_MethylPipeline_Fitness.md · 2026-07-10
      </Text>
    </Stack>
  );
}

function AssertionsSection() {
  return (
    <Stack gap={12}>
      <H2>Assertion-by-assertion</H2>
      <Text tone="secondary">
        Claim strength vs risk if applied naively to MethylPipeline.
      </Text>
      <Table
        headers={["Claim", "Support", "Risk"]}
        columnAlign={["left", "left", "left"]}
        rows={ASSERTIONS.map((a) => [
          a.claim,
          a.support,
          <Text tone="secondary">{a.risk}</Text>,
        ])}
        rowTone={ASSERTIONS.map((a) =>
          a.tone === "danger"
            ? "danger"
            : a.tone === "warning"
              ? "warning"
              : a.tone === "success"
                ? "success"
                : undefined
        )}
      />
    </Stack>
  );
}

function FeasibilitySection({
  filter,
  setFilter,
}: {
  filter: FeasibilityFilter;
  setFilter: (f: FeasibilityFilter) => void;
}) {
  const rows = FEASIBILITY.filter((r) => filter === "all" || r.bucket === filter);
  return (
    <Stack gap={12}>
      <Row gap={12} align="center" wrap>
        <H2>Recommendation feasibility</H2>
        <Select
          value={filter}
          onChange={(v) => setFilter(v as FeasibilityFilter)}
          options={(Object.keys(BUCKET_LABEL) as FeasibilityFilter[]).map((k) => ({
            value: k,
            label: BUCKET_LABEL[k],
          }))}
        />
      </Row>
      <Text tone="secondary" size="small">
        Showing {rows.length} of {FEASIBILITY.length} recommendations
      </Text>
      <Table
        headers={["Recommendation", "Bucket", "Detail"]}
        columnAlign={["left", "left", "left"]}
        rows={rows.map((r) => [
          r.rec,
          <Pill tone={BUCKET_PILL[r.bucket]} size="sm">
            {BUCKET_LABEL[r.bucket]}
          </Pill>,
          r.detail,
        ])}
      />
    </Stack>
  );
}

function FitnessSection() {
  return (
    <Stack gap={16}>
      <H2>Fitness vs ideal gatekeeper</H2>
      <Grid columns={2} gap={12}>
        <Card>
          <CardHeader>Fits today</CardHeader>
          <CardBody>
            <Stack gap={8}>
              {FITS_TODAY.map((t) => (
                <Text size="small">{t}</Text>
              ))}
            </Stack>
          </CardBody>
        </Card>
        <Card>
          <CardHeader trailing={<Pill tone="warning" size="sm">Gaps</Pill>}>
            Gaps
          </CardHeader>
          <CardBody>
            <Stack gap={8}>
              {GAPS.map((g) => (
                <Text size="small" tone="secondary">
                  {g}
                </Text>
              ))}
            </Stack>
          </CardBody>
        </Card>
      </Grid>
      <CollapsibleSection title="What NOT to do" defaultOpen={false}>
        <Stack gap={6}>
          {DO_NOT.map((d) => (
            <Text size="small" weight="semibold">
              {d}
            </Text>
          ))}
        </Stack>
      </CollapsibleSection>
      <Callout tone="info" title="Extension style">
        Prefer profile/site/program overlays + study manifests. Workers keep consuming
        resolvedConfig. No disease-specific Python defaults. No new SQL NodeTypes.
      </Callout>
    </Stack>
  );
}

function ExtensionsSection() {
  return (
    <Stack gap={12}>
      <H2>Top 5 extensions (impact vs effort)</H2>
      <Table
        headers={["#", "Extension", "Impact", "Effort", "Detail"]}
        columnAlign={["right", "left", "left", "left", "left"]}
        rows={EXTENSIONS.map((e) => [
          String(e.rank),
          e.title,
          e.impact,
          e.effort,
          e.detail,
        ])}
      />
      <Text tone="secondary" size="small">
        Honorable mention: paired cfdna + buffy_coat manifests for background control
        (config / study design).
      </Text>
    </Stack>
  );
}

function QuestionsSection() {
  return (
    <Stack gap={12}>
      <H2>Open questions</H2>
      <Text tone="secondary">Product / study-design decisions before implementation.</Text>
      <Stack gap={8}>
        {QUESTIONS.map((q, i) => (
          <Card>
            <CardBody>
              <Row gap={10} align="start">
                <Pill size="sm">{i + 1}</Pill>
                <Text>{q}</Text>
              </Row>
            </CardBody>
          </Card>
        ))}
      </Stack>
    </Stack>
  );
}

export default function PcaDetectionFitnessCanvas() {
  const [section, setSection] = useCanvasState<SectionId>("section", "verdict");
  const [filter, setFilter] = useCanvasState<FeasibilityFilter>("feasibilityFilter", "all");

  return (
    <Stack gap={20}>
      <Stack gap={8}>
        <H1>PCa Detection × MethylPipeline fitness</H1>
        <Text tone="secondary">
          Deep analysis of docs/research/Prostate Cancer Detection.md — assertions,
          recommendation feasibility, and pipeline extensions.
        </Text>
        <SectionNav active={section} onSelect={setSection} />
      </Stack>
      <Divider />
      {section === "verdict" && <VerdictSection />}
      {section === "assertions" && <AssertionsSection />}
      {section === "feasibility" && (
        <FeasibilitySection filter={filter} setFilter={setFilter} />
      )}
      {section === "fitness" && <FitnessSection />}
      {section === "extensions" && <ExtensionsSection />}
      {section === "questions" && <QuestionsSection />}
    </Stack>
  );
}
