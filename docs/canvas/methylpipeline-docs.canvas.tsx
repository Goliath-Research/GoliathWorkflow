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
  Text,
  computeDAGLayout,
  useCanvasAction,
  useHostTheme,
} from "cursor/canvas";

const AUDIENCE = [
  {
    role: "Operator",
    desc: "Run studies end-to-end",
    path: "docs/usage/index.qmd",
    chapter: "Usage Part II (ch.05–09)",
  },
  {
    role: "Statistician",
    desc: "Methods and assumptions",
    path: "docs/theory/chapters/03-methyldetector.qmd",
    chapter: "Theory ch.03 + limitations",
  },
  {
    role: "Developer",
    desc: "Engine, workers, compiler",
    path: "docs/implementation/index.md",
    chapter: "Implementation guide",
  },
  {
    role: "Workflow author",
    desc: "DomainPrograms and layers",
    path: "docs/reference/domain-program-language.md",
    chapter: "Reference + layer model",
  },
  {
    role: "DevOps",
    desc: "DB, gateway, cluster workers",
    path: "docs/usage/14-deployment-and-distributed-workflow.qmd",
    chapter: "Usage ch.14 + deployment runbook",
  },
];

const PILLARS = [
  {
    name: "Theory",
    path: "docs/theory/index.qmd",
    sections: [
      "Part I — Math (ch.01–10)",
      "Part II — Config semantics and workflow theory",
      "Limitations (ch.10)",
    ],
  },
  {
    name: "Usage",
    path: "docs/usage/index.qmd",
    sections: [
      "Setup and sample prep (ch.01–03)",
      "Staged workflow (ch.05–09)",
      "Ops and deployment (ch.10–15)",
    ],
  },
  {
    name: "Implementation",
    path: "docs/implementation/index.md",
    sections: [
      "Workflow engine",
      "Workers and gateway",
      "DomainProgram compiler",
      "Package IMPLEMENTATION index",
    ],
  },
];

const STAGES = [
  "Sample prep",
  "QC gates",
  "MC stability",
  "Freeze",
  "Model",
  "Validation",
  "Blind predict",
];

const LAYER_NODES = [
  { id: "manifest", label: "Study manifest" },
  { id: "profile", label: "Pipeline profile" },
  { id: "program", label: "DomainProgram" },
  { id: "instance", label: "Instance context" },
  { id: "worker", label: "Worker task" },
];

const LAYER_EDGES = [
  { from: "manifest", to: "instance" },
  { from: "profile", to: "worker" },
  { from: "program", to: "instance" },
  { from: "instance", to: "worker" },
];

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
      {children}
    </span>
  );
}

function LayerDiagram() {
  const theme = useHostTheme();
  const layout = computeDAGLayout({
    nodes: LAYER_NODES.map((n) => ({ id: n.id })),
    edges: LAYER_EDGES,
    direction: "horizontal",
    nodeWidth: 130,
    nodeHeight: 36,
    rankGap: 40,
    nodeGap: 16,
    padding: 8,
  });

  const labelById = Object.fromEntries(LAYER_NODES.map((n) => [n.id, n.label]));

  return (
    <svg
      width={layout.width}
      height={layout.height}
      style={{ display: "block", maxWidth: "100%" }}
      aria-label="Configuration layer model from manifest to worker"
    >
      <defs>
        <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
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
          markerEnd="url(#arrow)"
        />
      ))}
      {layout.nodes.map((n) => (
        <g key={n.id}>
          <rect
            x={n.x}
            y={n.y}
            width={130}
            height={36}
            rx={4}
            fill={theme.bg.elevated}
            stroke={theme.stroke.primary}
          />
          <text
            x={n.x + 65}
            y={n.y + 22}
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

export default function MethylPipelineDocsCanvas() {
  return (
    <Stack gap={24} style={{ padding: 24, maxWidth: 960 }}>
      <Stack gap={8}>
        <H1>MethylPipeline Documentation</H1>
        <Text tone="secondary">
          Monorepo for methylation workflows: MethylDetector in the ECDF path, DomainProgram
          orchestration via workflow engine and cluster workers.
        </Text>
        <Row gap={8}>
          <Pill tone="info">DomainProgram-first</Pill>
          <Pill tone="neutral">Theory · Usage · Implementation</Pill>
        </Row>
      </Stack>

      <Callout tone="info" title="Reading docs">
        Links open rendered Quarto HTML (Theory and Usage books) or Markdown source in the editor.
        Regenerate HTML after editing <Code>.qmd</Code> files:{" "}
        <Code>quarto render docs/theory docs/usage --to html</Code>
      </Callout>

      <Card>
        <CardHeader trailing={<Text tone="secondary" size="small">5 roles</Text>}>
          Choose your audience
        </CardHeader>
        <CardBody>
          <Grid columns={2} gap={12}>
            {AUDIENCE.map((a) => (
              <div key={a.role}>
                <Stack gap={4}>
                  <Text weight="semibold">{a.role}</Text>
                  <Text tone="secondary" size="small">
                    {a.desc}
                  </Text>
                  <DocLink path={a.path}>{a.chapter}</DocLink>
                </Stack>
              </div>
            ))}
          </Grid>
        </CardBody>
      </Card>

      <Stack gap={12}>
        <H2>Three pillars</H2>
        <Grid columns={3} gap={12}>
          {PILLARS.map((p) => (
            <div key={p.name}>
              <Card>
                <CardHeader trailing={<DocLink path={p.path}>Open</DocLink>}>{p.name}</CardHeader>
                <CardBody>
                  <Stack gap={4}>
                    {p.sections.map((s) => (
                      <div key={s}>
                        <Text size="small" tone="secondary">
                          {s}
                        </Text>
                      </div>
                    ))}
                  </Stack>
                </CardBody>
              </Card>
            </div>
          ))}
        </Grid>
      </Stack>

      <Stack gap={12}>
        <H2>System layer model</H2>
        <Text tone="secondary" size="small">
          manifest → profile → program → instance → worker. Source: docs/diagrams/src/layer-model.mmd
        </Text>
        <LayerDiagram />
        <DocLink path="docs/architecture/layer-model.md">Architecture: layer model</DocLink>
      </Stack>

      <Stack gap={12}>
        <H2>Pipeline stages</H2>
        <Row gap={8} style={{ flexWrap: "wrap", alignItems: "center" }}>
          {STAGES.map((stage, i) => (
            <div key={stage} style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Pill tone={i === 0 ? "info" : "neutral"}>{stage}</Pill>
              {i < STAGES.length - 1 ? (
                <Text tone="secondary" size="small">
                  →
                </Text>
              ) : null}
            </div>
          ))}
        </Row>
        <DocLink path="docs/architecture/pipeline-stages.md">Architecture: pipeline stages</DocLink>
      </Stack>

      <Grid columns={2} gap={12}>
        <Callout tone="info" title="Repo vs /work">
          DomainPrograms and profiles live in git. Study manifests and run artifacts live under{" "}
          <Code>/work/&lt;disease&gt;/</Code>.
        </Callout>
        <Callout tone="warning" title="Orchestration paths">
          Prefer <Code>methyl-workflow-run</Code>. Legacy{" "}
          <Code>methyl-validation --stability/--freeze/--model</Code> documented in Usage for
          transitional studies.
        </Callout>
      </Grid>

      <Divider />

      <Stack gap={8}>
        <H3>References</H3>
        <Row gap={16} style={{ flexWrap: "wrap" }}>
          <DocLink path="docs/index.md">docs/index.md</DocLink>
          <DocLink path="docs/DOCUMENTATION_AUDIT.md">Documentation audit</DocLink>
          <DocLink path="contracts/openapi.yaml">OpenAPI</DocLink>
          <DocLink path="docs/plans/README.md">Plans</DocLink>
          <DocLink path="docs/reference/documentation-toolchain.md">Toolchain decision</DocLink>
        </Row>
        <Text size="small" tone="secondary">
          Text hub for git and CI deep links; this canvas is the visual entry point.
        </Text>
      </Stack>
    </Stack>
  );
}
