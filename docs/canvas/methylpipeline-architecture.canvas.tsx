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
  useCanvasState,
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

function EndToEndDag() {
  const theme = useHostTheme();
  const nodes = [
    { id: "src", label: "fastqSource" },
    { id: "dl", label: "download" },
    { id: "aln", label: "align + QC" },
    { id: "ext", label: "extract h5" },
    { id: "arc", label: "archive" },
    { id: "dst", label: "sampleDest" },
    { id: "mc", label: "MC / freeze" },
    { id: "cov", label: "Ω + info" },
    { id: "mod", label: "model" },
    { id: "val", label: "holdouts" },
  ];
  const edges = [
    { from: "src", to: "dl" },
    { from: "dl", to: "aln" },
    { from: "aln", to: "ext" },
    { from: "ext", to: "arc" },
    { from: "arc", to: "dst" },
    { from: "arc", to: "mc" },
    { from: "mc", to: "cov" },
    { from: "cov", to: "mod" },
    { from: "mod", to: "val" },
  ];
  const layout = computeDAGLayout({
    nodes: nodes.map((n) => ({ id: n.id })),
    edges,
    direction: "horizontal",
    nodeWidth: 88,
    nodeHeight: 32,
    rankGap: 18,
    nodeGap: 8,
    padding: 6,
  });
  const labelById = Object.fromEntries(nodes.map((n) => [n.id, n.label]));
  const accent = new Set(["src", "dst", "cov", "val"]);

  return (
    <svg
      width={layout.width}
      height={layout.height}
      style={{ display: "block", maxWidth: "100%" }}
      aria-label="End-to-end: ingest through holdout validation"
    >
      <defs>
        <marker id="e2e-arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
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
          strokeWidth={1.4}
          markerEnd="url(#e2e-arrow)"
        />
      ))}
      {layout.nodes.map((n) => (
        <g key={n.id}>
          <rect
            x={n.x}
            y={n.y}
            width={88}
            height={32}
            rx={4}
            fill={accent.has(n.id) ? theme.fill.tertiary : theme.bg.elevated}
            stroke={accent.has(n.id) ? theme.accent.primary : theme.stroke.primary}
          />
          <text
            x={n.x + 44}
            y={n.y + 20}
            textAnchor="middle"
            fontSize={9}
            fill={theme.text.primary}
          >
            {labelById[n.id]}
          </text>
        </g>
      ))}
    </svg>
  );
}

function ConfigPrecedenceDiagram() {
  const theme = useHostTheme();
  const nodes = [
    { id: "site", label: "Site" },
    { id: "profile", label: "Profile" },
    { id: "program", label: "DomainProgram" },
    { id: "instance", label: "Instance" },
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
    nodeWidth: 110,
    nodeHeight: 34,
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
      aria-label="Configuration merge precedence"
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
            width={110}
            height={34}
            rx={4}
            fill={n.id === "resolved" ? theme.fill.tertiary : theme.bg.elevated}
            stroke={n.id === "resolved" ? theme.accent.primary : theme.stroke.primary}
          />
          <text
            x={n.x + 55}
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
  const h = 300;
  type Box = { x: number; y: number; w: number; h: number; label: string; sub?: string; accent?: boolean };
  const boxes: Box[] = [
    { x: 24, y: 20, w: 150, h: 52, label: "EpiPortal", sub: "portal.sp_*" },
    { x: 220, y: 20, w: 170, h: 64, label: "Central database", sub: "Azure SQL / PostgreSQL", accent: true },
    { x: 430, y: 20, w: 120, h: 52, label: "methyl-gateway", sub: "REST :8080" },
    { x: 580, y: 20, w: 120, h: 52, label: "Remote workers", sub: "methyl-worker" },
    { x: 220, y: 120, w: 340, h: 48, label: "wf schema engine", sub: "instances · leases · scope" },
    { x: 140, y: 210, w: 460, h: 52, label: "Shared /work", sub: "samples · projects · site · runtime-bundle" },
  ];
  const arrows: { x1: number; y1: number; x2: number; y2: number; label?: string }[] = [
    { x1: 174, y1: 46, x2: 220, y2: 46, label: "plan+start" },
    { x1: 390, y1: 46, x2: 430, y2: 46 },
    { x1: 550, y1: 46, x2: 580, y2: 46, label: "poll" },
    { x1: 305, y1: 84, x2: 305, y2: 120 },
    { x1: 490, y1: 72, x2: 490, y2: 120 },
    { x1: 640, y1: 72, x2: 640, y2: 236 },
    { x1: 640, y1: 236, x2: 600, y2: 236 },
    { x1: 390, y1: 168, x2: 390, y2: 210 },
  ];

  return (
    <svg width={w} height={h} style={{ display: "block", maxWidth: "100%" }} aria-label="Distributed runtime">
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
              y={(a.y1 + a.y2) / 2 - 5}
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
          <text x={b.x + b.w / 2} y={b.y + 20} textAnchor="middle" fontSize={11} fontWeight={600} fill={theme.text.primary}>
            {b.label}
          </text>
          {b.sub ? (
            <text x={b.x + b.w / 2} y={b.y + 36} textAnchor="middle" fontSize={9} fill={theme.text.secondary}>
              {b.sub}
            </text>
          ) : null}
        </g>
      ))}
      <text x={24} y={288} fontSize={9} fill={theme.text.secondary}>
        Workers never open SQL — they poll the gateway; portal and workers share /work paths
      </text>
    </svg>
  );
}

function LocalRuntimeDiagram() {
  const theme = useHostTheme();
  const boxes = [
    { x: 24, y: 28, w: 130, h: 44, label: "Developer / CI" },
    { x: 180, y: 28, w: 150, h: 44, label: "methyl-workflow-run" },
    { x: 356, y: 28, w: 160, h: 44, label: "LocalWorkflowEngine" },
    { x: 542, y: 28, w: 154, h: 44, label: "Same action handlers" },
  ];
  const xs = [154, 330, 516];

  return (
    <svg width={720} height={100} style={{ display: "block", maxWidth: "100%" }} aria-label="Local runtime">
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
              y1={50}
              x2={xs[i] + 26}
              y2={50}
              stroke={theme.stroke.primary}
              strokeWidth={1.5}
              markerEnd="url(#loc-arrow)"
            />
          ) : null}
          <rect x={b.x} y={b.y} width={b.w} height={b.h} rx={4} fill={theme.bg.elevated} stroke={theme.stroke.primary} />
          <text x={b.x + b.w / 2} y={b.y + 26} textAnchor="middle" fontSize={10} fill={theme.text.primary}>
            {b.label}
          </text>
        </g>
      ))}
      <text x={24} y={92} fontSize={9} fill={theme.text.secondary}>
        Same DomainPrograms and profiles; optional DB; artifacts under /work
      </text>
    </svg>
  );
}

/* ── Data ───────────────────────────────────────────────────────────────── */

type SectionId =
  | "overview"
  | "e2e"
  | "storage"
  | "paths"
  | "config"
  | "stages"
  | "db"
  | "refs";

const TOC: { id: SectionId; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "e2e", label: "End-to-end flow" },
  { id: "storage", label: "Dual storage" },
  { id: "paths", label: "Execution paths" },
  { id: "config", label: "Config layers" },
  { id: "stages", label: "Science stages" },
  { id: "db", label: "Database" },
  { id: "refs", label: "References" },
];

const STORAGE_ROWS = [
  ["fastqSource", "Ingress", "Lab / portal / NFS — FASTQs only"],
  ["/work/samples/{id}/", "Scratch", "FASTQ · BAM · QC · *.h5 · *.patterns.h5"],
  ["sampleDestination", "Egress", "qc/ · fastq/ · h5/ — never BAM"],
  ["/work/projects/{study}/", "Science", "MC · freeze · Ω · models · holdouts"],
];

const CONFIG_LAYERS = [
  ["Site", "/work/site/methyl_site.json", "Genomes, caches, deployment defaults"],
  ["Profile", "runtime-bundle/domain/profiles/*.profile.json", "Procedure packs + actionConfig"],
  ["Study", "/work/projects/<study>/configs/project_*.json", "Cohorts, partitions — no tool knobs"],
  ["DomainProgram", "workflow_engine/domain/**/*.program.json", "Control flow: for, if, parallel"],
  ["Instance", "wf.workflow_instance.context_json", "projectPath, profile, overlays"],
  ["Task", "input_json.resolvedConfig", "Merged params at worker claim"],
];

const PATH_COMPARE = [
  ["Entry", "methyl-workflow-run", "portal.sp_* / admin REST"],
  ["Scheduler", "LocalWorkflowEngine", "DB wf_engine_* procs"],
  ["Workers", "In-process handlers", "Gateway poll / submit"],
  ["Database", "Optional", "Azure SQL or PostgreSQL"],
  ["Use", "Dev · CI · smoke", "Production cluster"],
];

const STAGES = [
  { name: "Sample prep", detail: "download → align → QC → trim/realign → extract" },
  { name: "MC stability", detail: "centroid + detector iterations; holdouts excluded" },
  { name: "Freeze", detail: "fixed panels + mapper" },
  { name: "Covariates", detail: "derived · CellDeconv Ω · info_measures" },
  { name: "Model", detail: "ECDF ± second-stage covariates" },
  { name: "Holdouts", detail: "locked_test / pivotal_validation" },
];

const DB_OBJECTS = [
  ["wf.workflow_definition", "Compiled graph"],
  ["wf.workflow_instance", "Run + context_json"],
  ["wf.node_execution", "Task lease + result"],
  ["wf.scope_variable", "IF / FOREACH state"],
  ["portal.sp_create_and_start_instance", "Portal start without REST"],
];

/* ── Canvas ─────────────────────────────────────────────────────────────── */

export default function MethylPipelineArchitectureCanvas() {
  const [section, setSection] = useCanvasState<SectionId>("archSection", "overview");
  const theme = useHostTheme();

  return (
    <Stack gap={20} style={{ padding: 20, maxWidth: 980 }}>
      <Stack gap={8}>
        <H1>MethylPipeline architecture</H1>
        <Text tone="secondary">
          Interactive docs hub: ingest → SamplePrep → MC → DeConv/info covariates → model → holdouts,
          plus config layers and local vs distributed orchestration.
        </Text>
        <Row gap={8} style={{ flexWrap: "wrap" }}>
          <Pill tone="info">DomainProgram-first</Pill>
          <Pill tone="neutral">Config not code</Pill>
          <Pill tone="neutral">MSSQL · PostgreSQL</Pill>
        </Row>
      </Stack>

      <Card>
        <CardHeader trailing={<Pill tone="info">navigate</Pill>}>Table of contents</CardHeader>
        <CardBody>
          <Row gap={8} style={{ flexWrap: "wrap" }}>
            {TOC.map((t) => (
              <span key={t.id}>
                <Pill active={section === t.id} size="sm" onClick={() => setSection(t.id)}>
                  {t.label}
                </Pill>
              </span>
            ))}
          </Row>
        </CardBody>
      </Card>

      {section === "overview" ? (
        <Stack gap={16}>
          <H2>Overview</H2>
          <Grid columns={3} gap={12}>
            <Stat value="2" label="DomainPrograms (prep + study)" />
            <Stat value="2" label="Storage endpoints (in/out)" />
            <Stat value="2" label="Orchestration paths" />
          </Grid>
          <Callout tone="info" title="Audience">
            Operators, workflow authors, and DevOps. Markdown deep-dives live under{" "}
            <DocLink path="docs/architecture/index.md">docs/architecture/</DocLink>. This canvas is the
            navigable summary.
          </Callout>
          <Text>
            SamplePrep turns external FASTQs into durable{" "}
            <Code>{`{chrom}-{ctx}.h5`}</Code> (+ optional <Code>.patterns.h5</Code>). The study lifecycle
            then runs Monte Carlo stability, freezes panels, attaches CellDeconv Ω and MethylInfoTheory
            covariates, trains ECDF models, and evaluates holdouts.
          </Text>
        </Stack>
      ) : null}

      {section === "e2e" ? (
        <Stack gap={16}>
          <H2>End-to-end flow</H2>
          <EndToEndDag />
          <Text size="small" tone="secondary">
            Source: docs/architecture/end-to-end-workflow.md
          </Text>
          <Grid columns={2} gap={12}>
            <Card>
              <CardHeader>1 · SamplePrepPipeline</CardHeader>
              <CardBody>
                <Stack gap={6}>
                  <Text size="small">
                    Per sample (parallel): download → Parabricks → methyl_qc → optional trim/realign →
                    extract → archive → delete_fastqs (if <Code>deleteFastqs</Code>) → delete_bam
                  </Text>
                  <DocLink path="workflow_engine/domain/fixtures/sample_prep.program.json">
                    sample_prep.program.json
                  </DocLink>
                </Stack>
              </CardBody>
            </Card>
            <Card>
              <CardHeader>2 · Study validation lifecycle</CardHeader>
              <CardBody>
                <Stack gap={6}>
                  <Text size="small">
                    MC centroid/detector → stability → freeze → mapper → derived → cell_deconvolution →
                    info_measures → enricher → select_best_model → post_model_validation
                  </Text>
                  <DocLink path="workflow_engine/domain/fixtures/study_validation_lifecycle.program.json">
                    study_validation_lifecycle.program.json
                  </DocLink>
                </Stack>
              </CardBody>
            </Card>
          </Grid>
          <Callout tone="warning" title="Patterns optional">
            Missing <Code>*.patterns.h5</Code> does not fail the study — <Code>info_measures</Code> skips;
            covariate path lists omit absent CSVs.
          </Callout>
        </Stack>
      ) : null}

      {section === "storage" ? (
        <Stack gap={16}>
          <H2>Dual storage (ingress ≠ egress)</H2>
          <Table headers={["Location", "Role", "Contents"]} rows={STORAGE_ROWS} />
          <Callout tone="warning" title="BAM never archived">
            Alignments stay on <Code>/work</Code> only and are removed by <Code>delete_bam</Code>. Success
            archives <Code>mode=full</Code> (qc + fastq + h5); failure uses <Code>mode=qc_only</Code>.
          </Callout>
          <CollapsibleSection title="deleteFastqs flag" defaultOpen>
            <Stack gap={8}>
              <Text size="small">
                Default <Code>true</Code>: run <Code>sample.delete_fastqs</Code> after archive/terminal QC.
                Set instance <Code>deleteFastqs: false</Code> or profile{" "}
                <Code>actionConfig.sample_prep.delete_fastqs: false</Code> to retain FASTQs on scratch.
                Planner leaves the key unset so profile resolution can win.
              </Text>
              <DocLink path="workflow_engine/contract/sample_prep_capabilities.md">
                sample_prep_capabilities — FASTQ retention
              </DocLink>
            </Stack>
          </CollapsibleSection>
        </Stack>
      ) : null}

      {section === "paths" ? (
        <Stack gap={16}>
          <H2>Execution paths</H2>
          <Text tone="secondary" size="small">
            Same catalog actions and DomainPrograms; scheduling and transport differ.
          </Text>
          <CollapsibleSection title="Local — methyl-workflow-run" defaultOpen trailing={<Pill tone="info">dev</Pill>}>
            <Stack gap={10}>
              <LocalRuntimeDiagram />
              <Code>
                {`methyl-workflow-run --program …/study_validation_lifecycle.program.json --context '{"projectPath":"/work/projects/…/project.json","pipelineProfile":"samd_research"}'`}
              </Code>
            </Stack>
          </CollapsibleSection>
          <CollapsibleSection
            title="Distributed — portal + DB + gateway + workers"
            defaultOpen
            trailing={<Pill tone="neutral">prod</Pill>}
          >
            <Stack gap={10}>
              <DistributedRuntimeDiagram />
              <Callout tone="info" title="Transport split">
                Portal uses SQL (<Code>portal.sp_*</Code>). Workers poll <Code>methyl-gateway</Code> only —
                never open the database.
              </Callout>
            </Stack>
          </CollapsibleSection>
          <Table headers={["Dimension", "Local", "Distributed"]} rows={PATH_COMPARE} />
        </Stack>
      ) : null}

      {section === "config" ? (
        <Stack gap={16}>
          <H2>Configuration layers</H2>
          <Text tone="secondary" size="small">
            Highest wins: program/instance → profile actionConfig → analyte → site. No Python science
            defaults.
          </Text>
          <ConfigPrecedenceDiagram />
          <Table headers={["Layer", "Artifact", "Owns"]} rows={CONFIG_LAYERS} />
          <Row gap={12} style={{ flexWrap: "wrap" }}>
            <DocLink path="docs/architecture/layer-model.md">Layer model</DocLink>
            <DocLink path="docs/architecture/config-registry.md">Config registry</DocLink>
            <DocLink path="AGENTS.md">AGENTS.md</DocLink>
          </Row>
        </Stack>
      ) : null}

      {section === "stages" ? (
        <Stack gap={16}>
          <H2>Science stages</H2>
          <Row gap={6} style={{ flexWrap: "wrap", alignItems: "center" }}>
            {STAGES.map((s, i) => (
              <div key={s.name} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <Pill tone={i === 3 ? "info" : "neutral"}>{s.name}</Pill>
                {i < STAGES.length - 1 ? (
                  <Text tone="secondary" size="small">
                    →
                  </Text>
                ) : null}
              </div>
            ))}
          </Row>
          <Table
            headers={["Stage", "What happens"]}
            rows={STAGES.map((s) => [s.name, s.detail])}
          />
          <H3>Covariate fusion (ECDF)</H3>
          <Text size="small">
            First-stage ECDF stays methylation-only. Second-stage stacker fuses class probs with Ω (
            <Code>cell_fractions.csv</Code>), <Code>readlevel_measures.csv</Code>, and derived measures when
            listed on <Code>covariates_path</Code>. Auto-infer excludes <Code>group</Code> / QC columns.
          </Text>
          <DocLink path="docs/architecture/pipeline-stages.md">Pipeline stages</DocLink>
          {" · "}
          <DocLink path="docs/architecture/end-to-end-workflow.md">End-to-end workflow</DocLink>
        </Stack>
      ) : null}

      {section === "db" ? (
        <Stack gap={16}>
          <H2>Database contract</H2>
          <Text tone="secondary" size="small">
            Azure SQL and PostgreSQL share the same <Code>wf</Code> contract. Pick one primary backend per
            environment.
          </Text>
          <Grid columns={2} gap={12}>
            <Card>
              <CardHeader>Azure SQL</CardHeader>
              <CardBody>
                <Text size="small">Production portal + gateway. See workflow_engine/sql/</Text>
              </CardBody>
            </Card>
            <Card>
              <CardHeader>PostgreSQL</CardHeader>
              <CardBody>
                <Text size="small">Dev / parity. See workflow_engine/sql_pg/</Text>
              </CardBody>
            </Card>
          </Grid>
          <Table headers={["Object", "Role"]} rows={DB_OBJECTS} />
          <Table
            headers={["Step", "Actor", "Action"]}
            rows={[
              ["1", "Portal", "Create instance with enriched context_json"],
              ["2", "Engine", "READY node_execution + resolvedConfig"],
              ["3", "Worker", "Claim task via gateway"],
              ["4", "Worker", "Write /work artifacts; submit result"],
              ["5", "Engine", "Advance IF/FOREACH scope"],
            ]}
          />
        </Stack>
      ) : null}

      {section === "refs" ? (
        <Stack gap={16}>
          <H2>References</H2>
          <Stack gap={8}>
            <H3>Architecture markdown</H3>
            <Row gap={12} style={{ flexWrap: "wrap" }}>
              <DocLink path="docs/architecture/index.md">Index</DocLink>
              <DocLink path="docs/architecture/end-to-end-workflow.md">End-to-end</DocLink>
              <DocLink path="docs/architecture/distributed-runtime.md">Distributed runtime</DocLink>
              <DocLink path="docs/architecture/orchestration-paths.md">Orchestration paths</DocLink>
              <DocLink path="docs/architecture/layer-model.md">Layer model</DocLink>
            </Row>
            <H3>Usage</H3>
            <Row gap={12} style={{ flexWrap: "wrap" }}>
              <DocLink path="docs/usage/03-sample-prep-and-qc.qmd">ch.03 Sample prep</DocLink>
              <DocLink path="docs/usage/04-orchestration-workflow-run.qmd">ch.04 Orchestration</DocLink>
              <DocLink path="docs/usage/14-deployment-and-distributed-workflow.qmd">ch.14 Deploy</DocLink>
              <DocLink path="docs/usage/18-samd-study-lifecycle.qmd">ch.18 SaMD ladder</DocLink>
            </Row>
            <H3>Sister canvases</H3>
            <Text size="small" tone="secondary">
              Sync with <Code>bash scripts/sync_cursor_canvases.sh</Code>, then open from{" "}
              <Code>~/.cursor/projects/…/canvases/</Code> (not <Code>docs/canvas/</Code>) so Cursor renders
              the live panel instead of TypeScript source.
            </Text>
            <Row gap={12} style={{ flexWrap: "wrap" }}>
              <Text size="small">methylpipeline-docs · platform-overview · db-runbook</Text>
            </Row>
          </Stack>
          <Divider />
          <Text size="small" tone="secondary" style={{ color: theme.text.tertiary }}>
            Git source of truth: docs/canvas/methylpipeline-architecture.canvas.tsx
          </Text>
        </Stack>
      ) : null}
    </Stack>
  );
}
