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
  H3,
  Pill,
  Row,
  Stack,
  Stat,
  Table,
  Text,
  computeDAGLayout,
  useCanvasAction,
  useHostTheme,
} from "cursor/canvas";

function DocLink({ path, children }: { path: string; children?: string }) {
  const dispatch = useCanvasAction();
  const theme = useHostTheme();
  return (
    <span
      role="link"
      tabIndex={0}
      onClick={() => dispatch({ type: "openFile", path })}
      onKeyDown={(e: { key: string; preventDefault: () => void }) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          dispatch({ type: "openFile", path });
        }
      }}
      style={{
        color: theme.text.link,
        cursor: "pointer",
        textDecoration: "underline",
      }}
    >
      {children ?? path}
    </span>
  );
}

function CapabilityStackDiagram() {
  const theme = useHostTheme();
  const nodes = [
    { id: "users", label: "Authors / operators" },
    { id: "cfg", label: "Config + programs" },
    { id: "compile", label: "Validate + compile" },
    { id: "engine", label: "Engine / workers" },
    { id: "artifacts", label: "Artifacts + evidence" },
  ];
  const edges = [
    { from: "users", to: "cfg" },
    { from: "cfg", to: "compile" },
    { from: "compile", to: "engine" },
    { from: "engine", to: "artifacts" },
  ];
  const layout = computeDAGLayout({
    nodes: nodes.map((n) => ({ id: n.id })),
    edges,
    direction: "horizontal",
    nodeWidth: 126,
    nodeHeight: 36,
    rankGap: 24,
    nodeGap: 10,
    padding: 8,
  });
  const labelById = Object.fromEntries(nodes.map((n) => [n.id, n.label]));

  return (
    <svg
      width={layout.width}
      height={layout.height}
      style={{ display: "block", maxWidth: "100%" }}
      aria-label="Capability stack from authors to evidence"
    >
      <defs>
        <marker id="cap-arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
          <path d="M0,0 L0,6 L6,3 z" fill={theme.stroke.primary} />
        </marker>
      </defs>
      {layout.edges.map((e) => (
        <line
          key={`${e.from}-${e.to}`}
          x1={e.sourceX}
          y1={e.sourceY}
          x2={e.targetX}
          y2={e.targetY}
          stroke={theme.stroke.primary}
          strokeWidth={1.5}
          markerEnd="url(#cap-arrow)"
        />
      ))}
      {layout.nodes.map((n) => (
        <g key={n.id}>
          <rect
            x={n.x}
            y={n.y}
            width={126}
            height={36}
            rx={4}
            fill={n.id === "artifacts" ? theme.fill.tertiary : theme.bg.elevated}
            stroke={n.id === "artifacts" ? theme.accent.primary : theme.stroke.primary}
          />
          <text
            x={n.x + 63}
            y={n.y + 22}
            textAnchor="middle"
            fontSize={10}
            fill={theme.text.primary}
          >
            {labelById[n.id]}
          </text>
        </g>
      ))}
    </svg>
  );
}

function SamdLadderDiagram() {
  const theme = useHostTheme();
  const nodes = [
    { id: "research", label: "samd_research" },
    { id: "enrich", label: "holdout_enrichment" },
    { id: "pivotal", label: "samd_pivotal" },
  ];
  const edges = [
    { from: "research", to: "enrich" },
    { from: "enrich", to: "pivotal" },
  ];
  const layout = computeDAGLayout({
    nodes: nodes.map((n) => ({ id: n.id })),
    edges,
    direction: "horizontal",
    nodeWidth: 140,
    nodeHeight: 40,
    rankGap: 36,
    nodeGap: 12,
    padding: 8,
  });
  const labelById = Object.fromEntries(nodes.map((n) => [n.id, n.label]));

  return (
    <svg
      width={layout.width}
      height={layout.height}
      style={{ display: "block", maxWidth: "100%" }}
      aria-label="SaMD profile ladder"
    >
      <defs>
        <marker id="samd-arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
          <path d="M0,0 L0,6 L6,3 z" fill={theme.stroke.primary} />
        </marker>
      </defs>
      {layout.edges.map((e) => (
        <line
          key={`${e.from}-${e.to}`}
          x1={e.sourceX}
          y1={e.sourceY}
          x2={e.targetX}
          y2={e.targetY}
          stroke={theme.stroke.primary}
          strokeWidth={1.5}
          markerEnd="url(#samd-arrow)"
        />
      ))}
      {layout.nodes.map((n) => (
        <g key={n.id}>
          <rect
            x={n.x}
            y={n.y}
            width={140}
            height={40}
            rx={4}
            fill={n.id === "pivotal" ? theme.fill.tertiary : theme.bg.elevated}
            stroke={n.id === "pivotal" ? theme.accent.primary : theme.stroke.primary}
          />
          <text
            x={n.x + 70}
            y={n.y + 24}
            textAnchor="middle"
            fontSize={11}
            fill={theme.text.primary}
          >
            {labelById[n.id]}
          </text>
        </g>
      ))}
    </svg>
  );
}

function PipelineStageDiagram() {
  const theme = useHostTheme();
  const nodes = [
    { id: "prep", label: "Prep/QC" },
    { id: "stab", label: "Stability" },
    { id: "freeze", label: "Freeze" },
    { id: "model", label: "Model" },
    { id: "pmv", label: "Validate" },
    { id: "blind", label: "Predict" },
  ];
  const edges = [
    { from: "prep", to: "stab" },
    { from: "stab", to: "freeze" },
    { from: "freeze", to: "model" },
    { from: "model", to: "pmv" },
    { from: "pmv", to: "blind" },
  ];
  const layout = computeDAGLayout({
    nodes: nodes.map((n) => ({ id: n.id })),
    edges,
    direction: "horizontal",
    nodeWidth: 88,
    nodeHeight: 34,
    rankGap: 18,
    nodeGap: 8,
    padding: 8,
  });
  const labelById = Object.fromEntries(nodes.map((n) => [n.id, n.label]));

  return (
    <svg
      width={layout.width}
      height={layout.height}
      style={{ display: "block", maxWidth: "100%" }}
      aria-label="Scientific pipeline stages"
    >
      <defs>
        <marker id="stage-arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
          <path d="M0,0 L0,6 L6,3 z" fill={theme.stroke.secondary} />
        </marker>
      </defs>
      {layout.edges.map((e) => (
        <line
          key={`${e.from}-${e.to}`}
          x1={e.sourceX}
          y1={e.sourceY}
          x2={e.targetX}
          y2={e.targetY}
          stroke={theme.stroke.secondary}
          strokeWidth={1.25}
          markerEnd="url(#stage-arrow)"
        />
      ))}
      {layout.nodes.map((n) => (
        <g key={n.id}>
          <rect
            x={n.x}
            y={n.y}
            width={88}
            height={34}
            rx={4}
            fill={theme.bg.elevated}
            stroke={theme.stroke.primary}
          />
          <text
            x={n.x + 44}
            y={n.y + 21}
            textAnchor="middle"
            fontSize={10}
            fill={theme.text.primary}
          >
            {labelById[n.id]}
          </text>
        </g>
      ))}
    </svg>
  );
}

const TOC = [
  { id: "exec", title: "1. Executive overview" },
  { id: "caps", title: "2. Capability map" },
  { id: "author", title: "3. Workflow authoring" },
  { id: "config", title: "4. Configuration" },
  { id: "science", title: "5. Scientific process" },
  { id: "runtime", title: "6. Runtime & security" },
  { id: "samd", title: "7. SaMD fitness" },
  { id: "extend", title: "8. Extension path" },
  { id: "limits", title: "9. Limitations" },
];

const CAPABILITIES = [
  ["Sample prep / QC", "FASTQ → align → extract → archive"],
  ["Discovery / interpretation", "Centroid, detector, mapper, enricher"],
  ["Stability → model", "MC freeze, classifier, predictor"],
  ["Workflow platform", "DomainProgram, typed catalog, CAAS"],
  ["Distributed runtime", "Portal, cfg/wf DB, gateway, workers"],
  ["Evidence controls", "Partitions, claim gates, evidence index"],
];

const CONFIG_ROWS = [
  ["Site", "Genomes, caches, deployment caps"],
  ["Profile", "actionConfig packs + scope flags"],
  ["Study", "Cohorts, paths, partitions only"],
  ["Program", "Topology + optional overrides"],
];

const SAMD_ROWS = [
  ["samd_research", "Explore; early-stop; lock HPs"],
  ["samd_holdout_enrichment", "Requires locked_test; WF3"],
  ["samd_pivotal", "Requires pivotal_validation"],
];

export default function MethylPipelinePlatformOverviewCanvas() {
  const [active, setActive] = useCanvasState("section", "exec");

  return (
    <Stack gap={20} style={{ padding: 20, maxWidth: 1100 }}>
      <Stack gap={8}>
        <H1>MethylPipeline Platform Overview</H1>
        <Text tone="secondary">
          Navigable companion to the Markdown overview. Architecture supports
          controlled evidence generation — not FDA clearance by itself.
        </Text>
        <Row gap={8} style={{ flexWrap: "wrap" }}>
          <Pill tone="info">Schema-driven workflows</Pill>
          <Pill>Typed actions</Pill>
          <Pill>Four-layer config</Pill>
          <Pill tone="warning">Not a regulatory claim</Pill>
        </Row>
      </Stack>

      <Grid columns={4} gap={12}>
        <Stat value="~45" label="Catalog actions" />
        <Stat value="3" label="SaMD ladder profiles" tone="info" />
        <Stat value="WF3" label="True holdout path" />
        <Stat value="CAAS" label="Content-addressed reuse" />
      </Grid>

      <Callout tone="warning" title="Evidence boundary">
        Feasibility packages and architecture scaffolds are engineering evidence.
        Clinical performance claims require pivotal partitions, locked models, and
        a reviewed evidence package bound to a release SHA.
      </Callout>

      <Row gap={20} style={{ alignItems: "flex-start" }}>
        <Card style={{ width: 240, flexShrink: 0, position: "sticky", top: 12 }}>
          <CardHeader>Contents</CardHeader>
          <CardBody>
            <Stack gap={6}>
              {TOC.map((item) => (
                <Pill
                  key={item.id}
                  active={active === item.id}
                  onClick={() => setActive(item.id)}
                >
                  {item.title}
                </Pill>
              ))}
              <Divider />
              <DocLink path="docs/overview/methylpipeline-platform-overview.md">
                Open Markdown overview
              </DocLink>
            </Stack>
          </CardBody>
        </Card>

        <Stack gap={16} style={{ flex: 1, minWidth: 0 }}>
          {active === "exec" ? (
            <Stack gap={12}>
              <H2>Executive overview</H2>
              <Text>
                MethylPipeline is a schema-driven platform for describing, training,
                testing, and deploying workflows. The shipping process pack is DNA
                methylation analysis; new process types require typed action adapters.
              </Text>
              <CapabilityStackDiagram />
              <Text tone="secondary" style={{ fontSize: 12 }}>
                Source: platform overview §1 · Architecture layer model
              </Text>
            </Stack>
          ) : null}

          {active === "caps" ? (
            <Stack gap={12}>
              <H2>Capability map</H2>
              <Table
                headers={["Area", "Capability"]}
                rows={CAPABILITIES}
              />
              <DocLink path="docs/regulatory/methylpipeline-product-and-operational-controls.md">
                Product and operational controls
              </DocLink>
            </Stack>
          ) : null}

          {active === "author" ? (
            <Stack gap={12}>
              <H2>Workflow authoring</H2>
              <Text>
                Authors compose DomainPrograms from catalog actions. Prefer
                methyl-workflow-run; legacy methyl-validation stage flags are
                transitional only.
              </Text>
              <Code>
                {`methyl-workflow-run \\
  --program …/study_validation_lifecycle.program.json \\
  --context '{"projectPath":"…","pipelineProfile":"samd_research"}'`}
              </Code>
              <DocLink path="docs/reference/domain-program-language.md">
                DomainProgram language
              </DocLink>
            </Stack>
          ) : null}

          {active === "config" ? (
            <Stack gap={12}>
              <H2>Configuration and reproducibility</H2>
              <Table headers={["Layer", "Owns"]} rows={CONFIG_ROWS} />
              <Text>
                Precedence: instance/program → profile → analyte defaults → site.
                No Python fallback for tunable science knobs. Workers consume
                resolvedConfig.
              </Text>
              <DocLink path="docs/architecture/layer-model.md">Layer model</DocLink>
            </Stack>
          ) : null}

          {active === "science" ? (
            <Stack gap={12}>
              <H2>Scientific process pack</H2>
              <PipelineStageDiagram />
              <Text>
                Do not conflate WF2 random-split evaluation with WF3 classical
                holdouts on declared partitions.
              </Text>
              <DocLink path="docs/architecture/pipeline-stages.md">
                Pipeline stages
              </DocLink>
            </Stack>
          ) : null}

          {active === "runtime" ? (
            <Stack gap={12}>
              <H2>Runtime, operations, security</H2>
              <Grid columns={2} gap={12}>
                <Card>
                  <CardHeader>Distributed</CardHeader>
                  <CardBody>
                    <Text>
                      Portal SQL → cfg/wf DB → gateway ← workers; shared /work.
                      Gateway does not merge science config at claim.
                    </Text>
                  </CardBody>
                </Card>
                <Card>
                  <CardHeader>Observability</CardHeader>
                  <CardBody>
                    <Text>
                      DB node_execution, .action_results, JSONL timelines.
                      Central metrics/alerting not productized.
                    </Text>
                  </CardBody>
                </Card>
              </Grid>
              <DocLink path="docs/architecture/distributed-runtime.md">
                Distributed runtime
              </DocLink>
            </Stack>
          ) : null}

          {active === "samd" ? (
            <Stack gap={12}>
              <H2>SaMD fitness framework</H2>
              <SamdLadderDiagram />
              <Table headers={["Profile", "Intent"]} rows={SAMD_ROWS} />
              <Callout tone="info" title="Code-enforced claim gate">
                allow_clinical_performance_claims is blocked before
                pivotal_validation stage.
              </Callout>
              <Row gap={12} style={{ flexWrap: "wrap" }}>
                <DocLink path="docs/usage/18-samd-study-lifecycle.qmd">
                  SaMD lifecycle SOP
                </DocLink>
                <DocLink path="docs/regulatory/validation-evidence-index.md">
                  Evidence index
                </DocLink>
              </Row>
            </Stack>
          ) : null}

          {active === "extend" ? (
            <Stack gap={12}>
              <H2>Extension path</H2>
              <Text>
                New workflows: define Pydantic I/O → export schemas → register
                action → compose DomainProgram → site/profile knobs → local test →
                deploy → manifests/evidence.
              </Text>
              <H3>Anti-patterns</H3>
              <Text tone="secondary">
                Hidden DEFAULT_* science constants · workers re-reading study
                manifests · long-lived keys in task JSON · citing stub runs as
                clinical evidence
              </Text>
            </Stack>
          ) : null}

          {active === "limits" ? (
            <Stack gap={12}>
              <H2>Limitations and readiness</H2>
              <Grid columns={3} gap={12}>
                <Card>
                  <CardHeader>Implemented</CardHeader>
                  <CardBody>
                    <Text>Compile/run, typed catalog, config layers, SaMD profiles, CAAS</Text>
                  </CardBody>
                </Card>
                <Card>
                  <CardHeader>Scaffolded</CardHeader>
                  <CardBody>
                    <Text>Regulatory synthesis pending formal QMS; PCCP drafts</Text>
                  </CardBody>
                </Card>
                <Card>
                  <CardHeader>Evidence-bound</CardHeader>
                  <CardBody>
                    <Text>Must cite release SHA, partitions, metrics in evidence packages</Text>
                  </CardBody>
                </Card>
              </Grid>
              <DocLink path="docs/regulatory/README.md">Regulatory pillar</DocLink>
            </Stack>
          ) : null}
        </Stack>
      </Row>
    </Stack>
  );
}
