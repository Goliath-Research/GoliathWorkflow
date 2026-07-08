import {
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
  computeDAGLayout,
  useCanvasAction,
  useHostTheme,
} from "cursor/canvas";

/* ── Doc links ─────────────────────────────────────────────────────────── */

function renderedDocPath(sourcePath: string): string {
  if (!sourcePath.endsWith(".qmd")) return sourcePath;
  if (sourcePath.startsWith("docs/theory/")) {
    return (
      "docs/theory/_book/" +
      sourcePath.slice("docs/theory/".length).replace(/\.qmd$/, ".html")
    );
  }
  if (sourcePath.startsWith("docs/usage/")) {
    return (
      "docs/usage/_book/" +
      sourcePath.slice("docs/usage/".length).replace(/\.qmd$/, ".html")
    );
  }
  return sourcePath;
}

function DocLink({ path, children }: { path: string; children?: string }) {
  const dispatch = useCanvasAction();
  const theme = useHostTheme();
  const target = renderedDocPath(path);

  return (
    <span
      role="link"
      tabIndex={0}
      onClick={() => dispatch({ type: "openFile", path: target })}
      onKeyDown={(e: { key: string; preventDefault: () => void }) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          dispatch({ type: "openFile", path: target });
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

/* ── Diagrams ─────────────────────────────────────────────────────────── */

function ConfigPrecedenceDiagram() {
  const theme = useHostTheme();
  const nodes = [
    { id: "site", label: "Site manifest" },
    { id: "profile", label: "Profile" },
    { id: "program", label: "DomainProgram" },
    { id: "instance", label: "Instance context" },
    { id: "resolved", label: "resolvedConfig" },
  ];
  const edges = [
    { from: "site", to: "profile" },
    { from: "profile", to: "program" },
    { from: "program", to: "instance" },
    { from: "instance", to: "resolved" },
  ];
  const layout = computeDAGLayout({
    nodes: nodes.map((n) => ({ id: n.id })),
    edges,
    direction: "horizontal",
    nodeWidth: 118,
    nodeHeight: 34,
    rankGap: 28,
    nodeGap: 10,
    padding: 8,
  });
  const labelById = Object.fromEntries(nodes.map((n) => [n.id, n.label]));

  return (
    <svg
      width={layout.width}
      height={layout.height}
      style={{ display: "block", maxWidth: "100%" }}
      aria-label="Configuration merge precedence from site to worker task"
    >
      <defs>
        <marker id="cfg-arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
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
          markerEnd="url(#cfg-arrow)"
        />
      ))}
      {layout.nodes.map((n) => (
        <g key={n.id}>
          <rect
            x={n.x}
            y={n.y}
            width={118}
            height={34}
            rx={4}
            fill={n.id === "resolved" ? theme.fill.tertiary : theme.bg.elevated}
            stroke={n.id === "resolved" ? theme.accent.primary : theme.stroke.primary}
          />
          <text
            x={n.x + 59}
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

function DistributedRuntimeDiagram() {
  const theme = useHostTheme();
  const w = 720;
  const h = 340;

  type Box = { x: number; y: number; w: number; h: number; label: string; sub?: string; accent?: boolean };
  const boxes: Box[] = [
    { x: 24, y: 24, w: 150, h: 56, label: "EpiPortal / operator", sub: "SQL direct (portal.sp_*)" },
    { x: 220, y: 24, w: 170, h: 72, label: "Central database", sub: "Azure SQL or PostgreSQL", accent: true },
    { x: 430, y: 24, w: 130, h: 56, label: "methyl-gateway", sub: "REST :8080" },
    { x: 590, y: 24, w: 110, h: 56, label: "Remote workers", sub: "methyl-worker" },
    { x: 220, y: 140, w: 340, h: 52, label: "wf schema engine", sub: "instances, node_execution, scope, leases" },
    { x: 120, y: 240, w: 480, h: 56, label: "Shared /work storage", sub: "samples, HDF5, monte_carlo_runs, site manifest" },
  ];

  type Arrow = { x1: number; y1: number; x2: number; y2: number; label?: string };
  const arrows: Arrow[] = [
    { x1: 174, y1: 52, x2: 220, y2: 52, label: "plan + start" },
    { x1: 390, y1: 52, x2: 430, y2: 52, label: "admin deploy" },
    { x1: 560, y1: 52, x2: 590, y2: 52, label: "poll/submit" },
    { x1: 495, y1: 80, x2: 495, y2: 140 },
    { x1: 305, y1: 96, x2: 305, y2: 140 },
    { x1: 645, y1: 80, x2: 645, y2: 200 },
    { x1: 645, y1: 200, x2: 495, y2: 200 },
    { x1: 495, y1: 192, x2: 495, y2: 240 },
    { x1: 645, y1: 200, x2: 645, y2: 268 },
    { x1: 645, y1: 268, x2: 600, y2: 268 },
  ];

  return (
    <svg width={w} height={h} style={{ display: "block", maxWidth: "100%" }} aria-label="Distributed runtime: portal, database, gateway, workers, shared storage">
      <defs>
        <marker id="rt-arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
          <path d="M0,0 L0,6 L6,3 z" fill={theme.stroke.secondary} />
        </marker>
      </defs>
      {arrows.map((a, i) => (
        <g key={i}>
          <line
            x1={a.x1}
            y1={a.y1}
            x2={a.x2}
            y2={a.y2}
            stroke={theme.stroke.secondary}
            strokeWidth={1.25}
            markerEnd="url(#rt-arrow)"
          />
          {a.label ? (
            <text
              x={(a.x1 + a.x2) / 2}
              y={(a.y1 + a.y2) / 2 - 6}
              textAnchor="middle"
              fontSize={9}
              fill={theme.text.secondary}
            >
              {a.label}
            </text>
          ) : null}
        </g>
      ))}
      {boxes.map((b) => (
        <g key={b.label}>
          <rect
            x={b.x}
            y={b.y}
            width={b.w}
            height={b.h}
            rx={4}
            fill={b.accent ? theme.fill.tertiary : theme.bg.elevated}
            stroke={b.accent ? theme.accent.primary : theme.stroke.primary}
          />
          <text x={b.x + b.w / 2} y={b.y + 22} textAnchor="middle" fontSize={11} fontWeight={600} fill={theme.text.primary}>
            {b.label}
          </text>
          {b.sub ? (
            <text x={b.x + b.w / 2} y={b.y + 38} textAnchor="middle" fontSize={9} fill={theme.text.secondary}>
              {b.sub}
            </text>
          ) : null}
        </g>
      ))}
      <text x={24} y={328} fontSize={9} fill={theme.text.secondary}>
        Portal does not dispatch workers in production — workers poll the gateway; both read/write /work
      </text>
    </svg>
  );
}

function LocalRuntimeDiagram() {
  const theme = useHostTheme();
  const w = 720;
  const h = 120;
  const boxes = [
    { x: 24, y: 32, w: 130, h: 48, label: "Developer / CI" },
    { x: 180, y: 32, w: 150, h: 48, label: "methyl-workflow-run" },
    { x: 356, y: 32, w: 160, h: 48, label: "LocalWorkflowEngine" },
    { x: 542, y: 32, w: 154, h: 48, label: "Same action handlers" },
  ];
  const xs = [154, 330, 516, 696];

  return (
    <svg width={w} height={h} style={{ display: "block", maxWidth: "100%" }} aria-label="Local runtime path">
      <defs>
        <marker id="loc-arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
          <path d="M0,0 L0,6 L6,3 z" fill={theme.stroke.primary} />
        </marker>
      </defs>
      {boxes.map((b, i) => (
        <g key={b.label}>
          {i < boxes.length - 1 ? (
            <line
              x1={xs[i]}
              y1={56}
              x2={xs[i] + 26}
              y2={56}
              stroke={theme.stroke.primary}
              strokeWidth={1.5}
              markerEnd="url(#loc-arrow)"
            />
          ) : null}
          <rect x={b.x} y={b.y} width={b.w} height={b.h} rx={4} fill={theme.bg.elevated} stroke={theme.stroke.primary} />
          <text x={b.x + b.w / 2} y={b.y + 28} textAnchor="middle" fontSize={10} fill={theme.text.primary}>
            {b.label}
          </text>
        </g>
      ))}
      <text x={24} y={104} fontSize={9} fill={theme.text.secondary}>
        Same DomainPrograms and profiles as production; optional DB; artifacts under /work
      </text>
    </svg>
  );
}

/* ── Data ───────────────────────────────────────────────────────────────── */

const STAGES = [
  { name: "Sample prep", pkg: "workers, alignment QC, extract" },
  { name: "QC gates", pkg: "methylalignmentqc, methylextractionqc" },
  { name: "MC stability", pkg: "centroid, detector, validation" },
  { name: "Freeze", pkg: "mapper, enricher, progression" },
  { name: "Model", pkg: "classifier, predictor" },
  { name: "Validation", pkg: "methylvalidation" },
  { name: "Blind predict", pkg: "methylpredictor" },
];

const CONFIG_LAYERS = [
  ["Site", "/work/site/methyl_site.json", "Genomes, caches, deployment-wide actionConfig defaults"],
  ["Profile", "runtime-bundle/domain/profiles/*.profile.json", "Procedure packs: actionConfig + scope booleans"],
  ["Study manifest", "/work/projects/<study>/configs/project_*.json", "Cohorts, paths, regulatory — no tool params"],
  ["DomainProgram", "workflow_engine/domain/**/*.program.json", "Control flow: for, if, parallel, do"],
  ["Instance", "wf.workflow_instance.context_json", "projectPath, pipelineProfile, per-run overlays"],
  ["Task", "node_execution.input_json.resolvedConfig", "Merged params at worker claim time"],
];

const STORAGE_ROWS = [
  ["Git repo / runtime-bundle", "DomainPrograms, profiles, schemas, action catalog"],
  ["/work/site/", "methyl_site.json — cluster defaults"],
  ["/work/projects/<study>/", "project_*.json, data CSVs"],
  ["/work/projects/<study>/<name>/", "monte_carlo_runs/, stability/, model bundles"],
  ["/work/samples/<id>/", "Flat sample archive (FASTQ, BAM, HDF5)"],
  ["/work/epimethyl/current/", "Promoted release: venv, env, runtime-bundle"],
];

const DB_OBJECTS = [
  ["wf.workflow_definition", "Compiled graph (nodes, FOREACH, bindings)"],
  ["wf.workflow_instance", "Running study run; context_json + status"],
  ["wf.node_execution", "Per-action task row; input_json, result_code, lease"],
  ["wf.scope_variable", "IF / FOREACH branch state"],
  ["wf.workflow_action", "Catalog capability → handler metadata"],
  ["portal.sp_create_and_start_instance", "Portal middle-tier: plan + start without REST"],
  ["portal.resource_profile", "Archive / S3 defaults for sample prep"],
];

const PATH_COMPARE = [
  ["Entry", "methyl-workflow-run --program … --context …", "portal.sp_* or admin POST /v1/workflows/instances"],
  ["Scheduler", "LocalWorkflowEngine (in-process thread pool)", "DB stored procedures (wf_engine_*)"],
  ["Worker transport", "Direct handler dispatch", "POST /v1/workers/tasks/request|submit"],
  ["Database", "Optional (none for pure local)", "Azure SQL or PostgreSQL (same wf contract)"],
  ["Config source", "Profile file + site manifest + context", "Enriched context_json in DB + mc_config snapshot"],
  ["Artifacts", "Shared /work paths", "Same /work layout (NFS/object mount)"],
  ["Typical use", "Dev, smoke, debugging single programs", "Production cluster, GPU workers, portal UI"],
];

/* ── Canvas ─────────────────────────────────────────────────────────────── */

export default function MethylPipelineArchitectureCanvas() {
  return (
    <Stack gap={28} style={{ padding: 24, maxWidth: 980 }}>
      <Stack gap={8}>
        <H1>MethylPipeline Architecture</H1>
        <Text tone="secondary">
          Disease-agnostic methylation workflow platform: four-layer configuration, shared /work storage,
          and two orchestration paths — local in-process engine vs distributed gateway + database + remote workers.
        </Text>
        <Row gap={8} style={{ flexWrap: "wrap" }}>
          <Pill tone="info">DomainProgram-first</Pill>
          <Pill tone="neutral">MSSQL · PostgreSQL</Pill>
          <Pill tone="neutral">Config not code</Pill>
        </Row>
      </Stack>

      <Grid columns={3} gap={12}>
        <Stat value="4+" label="Config layers" />
        <Stat value="2" label="Orchestration paths" />
        <Stat value="7" label="Science stages" />
      </Grid>

      {/* ── Execution paths ── */}
      <Stack gap={16}>
        <H2>Execution paths</H2>
        <Text tone="secondary" size="small">
          Both paths run the same catalog actions and DomainPrograms; only scheduling and transport differ.
        </Text>

        <CollapsibleSection
          title="Local — methyl-workflow-run"
          defaultOpen
          trailing={<Pill tone="info">dev · CI · smoke</Pill>}
        >
          <Stack gap={12}>
            <LocalRuntimeDiagram />
            <Text size="small">
              Compiles or loads a DomainProgram, expands <Code>context_json</Code>, materializes{" "}
              <Code>resolvedConfig</Code> per action, executes handlers in-process. Use{" "}
              <Code>--parallel-workers 1</Code> on NFS/GPU. No gateway required.
            </Text>
            <Code>methyl-workflow-run --program …/buffy_mc_stability.program.json --context-file …/mc_gene_fc.profile.json --context '{`{"projectPath":"/work/projects/…/project.json"}`}'</Code>
          </Stack>
        </CollapsibleSection>

        <CollapsibleSection
          title="Distributed — portal + database + gateway + workers"
          defaultOpen
          trailing={<Pill tone="neutral">production</Pill>}
        >
          <Stack gap={12}>
            <DistributedRuntimeDiagram />
            <Callout tone="info" title="Transport split">
              EpiPortal talks to the database directly (<Code>portal.sp_*</Code>). Remote workers never
              connect to SQL — they poll <Code>methyl-gateway</Code> only. Both portal and workers read/write
              the same <Code>/work</Code> paths referenced in <Code>context_json</Code>.
            </Callout>
          </Stack>
        </CollapsibleSection>

        <Table
          headers={["Dimension", "Local", "Distributed (gateway)"]}
          rows={PATH_COMPARE}
        />
      </Stack>

      <Divider />

      {/* ── Configuration dimensions ── */}
      <Stack gap={12}>
        <H2>Configuration dimensions</H2>
        <Text tone="secondary" size="small">
          Precedence (highest wins): program/instance override → profile actionConfig → analyte defaults → site
          actionConfig. No Python fallbacks for tunable science parameters.
        </Text>
        <ConfigPrecedenceDiagram />
        <Table headers={["Layer", "Artifact", "Owns"]} rows={CONFIG_LAYERS} />
        <DocLink path="docs/architecture/layer-model.md">Layer model (architecture doc)</DocLink>
        {" · "}
        <DocLink path="AGENTS.md">AGENTS.md — config-not-code principles</DocLink>
      </Stack>

      <Divider />

      {/* ── Storage ── */}
      <Stack gap={12}>
        <H2>Storage layout (/work vs repo)</H2>
        <Table headers={["Location", "Contents"]} rows={STORAGE_ROWS} />
        <Callout tone="warning" title="Production rule">
          Workers use <Code>/work/epimethyl/current/runtime-bundle/</Code> for profiles and programs — not a
          git checkout. Study science lives under <Code>/work/projects/&lt;study&gt;/</Code>.
        </Callout>
      </Stack>

      <Divider />

      {/* ── Science pipeline ── */}
      <Stack gap={12}>
        <H2>Science pipeline (study lifecycle)</H2>
        <Row gap={6} style={{ flexWrap: "wrap", alignItems: "center" }}>
          {STAGES.map((s, i) => (
            <div key={s.name} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <Pill tone={i === 2 ? "info" : "neutral"}>{s.name}</Pill>
              {i < STAGES.length - 1 ? (
                <Text tone="secondary" size="small">
                  →
                </Text>
              ) : null}
            </div>
          ))}
        </Row>
        <Grid columns={2} gap={8}>
          {STAGES.map((s) => (
            <div key={s.name}>
              <Text size="small" tone="secondary">
                <Text weight="semibold" size="small">
                  {s.name}
                </Text>
                {" — "}
                {s.pkg}
              </Text>
            </div>
          ))}
        </Grid>
        <DocLink path="docs/architecture/pipeline-stages.md">Pipeline stages</DocLink>
      </Stack>

      <Divider />

      {/* ── Database contract ── */}
      <Stack gap={12}>
        <H2>Database contract (dual backend)</H2>
        <Text tone="secondary" size="small">
          Azure SQL and PostgreSQL implement the same <Code>wf</Code> schema. Choose one primary backend per
          environment; CI and dev often use PostgreSQL.
        </Text>
        <Grid columns={2} gap={12}>
          <Card>
            <CardHeader>Azure SQL</CardHeader>
            <CardBody>
              <Stack gap={6}>
                <Text size="small">Production gateway + portal; scripts under workflow_engine/sql/</Text>
                <DocLink path="workflow_engine/sql/README.md">sql/README.md</DocLink>
              </Stack>
            </CardBody>
          </Card>
          <Card>
            <CardHeader>PostgreSQL</CardHeader>
            <CardBody>
              <Stack gap={6}>
                <Text size="small">Parity / dev; deploy via sql_pg/deploy_azure.sh</Text>
                <DocLink path="workflow_engine/sql_pg/README.md">sql_pg/README.md</DocLink>
              </Stack>
            </CardBody>
          </Card>
        </Grid>
        <Table headers={["Object", "Role"]} rows={DB_OBJECTS} />
      </Stack>

      <Divider />

      {/* ── Worker task flow ── */}
      <Stack gap={12}>
        <H3>Worker task flow (distributed)</H3>
        <Table
          headers={["Step", "Actor", "Action"]}
          rows={[
            ["1", "Portal / admin", "Create workflow_instance with enriched context_json (projectPath, actionConfig)"],
            ["2", "Engine (DB)", "Materialize READY node_execution rows; bind input_json + resolvedConfig"],
            ["3", "Worker", "POST /v1/workers/tasks/request with capability (e.g. methyl-detector)"],
            ["4", "Gateway → DB", "sp_worker_request_task — lease task or empty"],
            ["5", "Worker", "Run package CLI; write artifacts to /work; optional action manifest"],
            ["6", "Worker", "POST /v1/workers/tasks/{id}/submit with result_code + output_json"],
            ["7", "Engine (DB)", "Update scope_variable; activate IF/FOREACH downstream nodes"],
          ]}
        />
        <Row gap={16} style={{ flexWrap: "wrap" }}>
          <DocLink path="workers/WORKER_PROTOCOL.md">Worker protocol</DocLink>
          <DocLink path="contracts/openapi.yaml">OpenAPI contract</DocLink>
          <DocLink path="docs/usage/14-deployment-and-distributed-workflow.qmd">Deployment ch.14</DocLink>
          <DocLink path="docs/architecture/distributed-runtime.md">Distributed runtime</DocLink>
        </Row>
      </Stack>

      <Divider />

      <Stack gap={8}>
        <H3>Related canvases & docs</H3>
        <Row gap={16} style={{ flexWrap: "wrap" }}>
          <DocLink path="docs/architecture/index.md">Architecture index</DocLink>
          <DocLink path="docs/architecture/orchestration-paths.md">Orchestration paths</DocLink>
          <DocLink path="docs/reference/domain-program-language.md">DomainProgram reference</DocLink>
          <DocLink path="docs/reference/config-parameter-matrix.md">Config parameter matrix</DocLink>
        </Row>
        <Text size="small" tone="secondary">
          Also see methylpipeline-docs.canvas.tsx (documentation hub) and methylpipeline-db-runbook.canvas.tsx
          (DB bootstrap).
        </Text>
      </Stack>
    </Stack>
  );
}
