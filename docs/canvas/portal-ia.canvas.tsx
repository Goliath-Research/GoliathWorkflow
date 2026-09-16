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

function PipelineDag() {
  const theme = useHostTheme();
  const nodes = [
    { id: "cohort", label: "Cohort" },
    { id: "storage", label: "Storage" },
    { id: "prep", label: "SamplePrep" },
    { id: "life", label: "Lifecycle" },
    { id: "pred", label: "Prediction" },
  ];
  const edges = [
    { from: "cohort", to: "storage" },
    { from: "storage", to: "prep" },
    { from: "prep", to: "life" },
    { from: "life", to: "pred" },
  ];
  const layout = computeDAGLayout({
    nodes: nodes.map((n) => ({ id: n.id })),
    edges,
    direction: "horizontal",
    nodeWidth: 100,
    nodeHeight: 34,
    rankGap: 22,
    nodeGap: 10,
    padding: 8,
  });
  const labelById = Object.fromEntries(nodes.map((n) => [n.id, n.label]));
  const accent = new Set(["prep", "life"]);

  return (
    <svg
      width={layout.width}
      height={layout.height}
      role="img"
      aria-label="Study pipeline stages from cohort through optional prediction"
    >
      {layout.edges.map((e) => (
        <line
          key={`${e.from}-${e.to}`}
          x1={e.sourceX}
          y1={e.sourceY}
          x2={e.targetX}
          y2={e.targetY}
          stroke={theme.stroke.secondary}
          strokeWidth={1}
        />
      ))}
      {layout.nodes.map((n) => {
        const isAccent = accent.has(n.id);
        return (
          <g key={n.id}>
            <rect
              x={n.x}
              y={n.y}
              width={100}
              height={34}
              rx={4}
              fill={isAccent ? theme.fill.tertiary : theme.fill.secondary}
              stroke={theme.stroke.primary}
            />
            <text
              x={n.x + 50}
              y={n.y + 22}
              textAnchor="middle"
              fill={theme.text.primary}
              fontSize={11}
            >
              {labelById[n.id]}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export default function PortalIaCanvas() {
  return (
    <Stack gap={24} style={{ padding: 24, maxWidth: 1100 }}>
      <Stack gap={8}>
        <H1>EpiPortal pipeline IA</H1>
        <Text tone="secondary">
          Spec for the other repo: Study workspace, instance monitor and retry,
          Admin RBAC, and contract process packs. MethylPipeline owns{" "}
          <Code>portal.sp_*</Code> SQL contracts, not Delphi/uniGUI screens.
        </Text>
        <Row gap={8}>
          <DocLink path="docs/architecture/portal-ia.md">portal-ia.md</DocLink>
          <Text tone="tertiary">·</Text>
          <DocLink path="docs/plans/portal-pipeline-ia.plan.md">plan</DocLink>
          <Text tone="tertiary">·</Text>
          <DocLink path="docs/usage/11-troubleshooting-and-recovery.md">
            usage ch.11
          </DocLink>
        </Row>
      </Stack>

      <Grid columns={4} gap={12}>
        <Stat value="6" label="Top-level nav items" />
        <Stat value="3" label="Process packs" />
        <Stat value="FAILED→READY" label="Operator retry" />
        <Stat value="portal.sp_*" label="UI SQL contract" />
      </Grid>

      <Callout tone="info" title="Control layers stay distinct">
        Fleet Drain/Stop is not instance pause. Instance pause is not task Retry.
        Retry is not a new study run. Cluster deployment is not Study Storage.
        Missing FASTQ is an external upload to the same source URI, then Retry —
        the portal does not upload files.
      </Callout>

      <H2>Navigation</H2>
      <Table
        striped
        headers={["Nav", "Audience", "Primary screens"]}
        rows={[
          ["Home / Ops", "Operator / infra", "Instances, stale leases, fleet strip"],
          ["Studies", "Operator / study lead", "Pipeline workspace + Runs monitor"],
          ["Workflows", "Program author / platform admin", "Graph edit + publish — hidden from operator/lead"],
          ["Platform", "Lab / system admin", "Site + Guardrails, packs + Guardrails, storage, cluster deployment, fleet"],
          ["Hyperparameters", "Study lead", "Grids and trials"],
          ["Admin", "Platform admin", "RBAC + Contracts (process packs)"],
        ]}
        rowTone={["info", "success", undefined, undefined, undefined, "warning"]}
      />

      <H2>Study pipeline</H2>
      <PipelineDag />
      <Text tone="tertiary" size="small">
        Operator path. Contracts filter catalogs before SamplePrep and lifecycle
        starts. Blind prediction is optional and is not a validation accuracy claim.
      </Text>

      <Grid columns={2} gap={16}>
        <Card>
          <CardHeader>Study screens</CardHeader>
          <CardBody>
            <Table
              framed={false}
              headers={["Screen", "Proc"]}
              rows={[
                ["Overview", "sp_get_study_pipeline_progress"],
                ["Cohort / arms", "sp_set_study_group_members"],
                ["Storage pick", "sp_get/set_study_storage"],
                ["Guardrails (next run)", "sp_get/set_study_guardrails_editor"],
                ["Runs", "sp_list_study_instances"],
                ["Instance", "sp_get_workflow_instance_header + tasks"],
                ["Sample matrix", "sp_get_instance_sample_progress"],
                ["Config snapshot", "sp_get_instance_config"],
                ["Task detail", "sp_get_node_execution_detail"],
                ["Retry", "sp_retry_failed_node"],
                ["Start next", "catalogs + sp_create_and_start_instance"],
              ]}
            />
          </CardBody>
        </Card>
        <Card>
          <CardHeader>Recovery verbs</CardHeader>
          <CardBody>
            <Stack gap={8}>
              <Row gap={8}>
                <Pill tone="warning" size="sm">
                  Reclaim
                </Pill>
                <Text>RUNNING + expired lease → sp_reclaim_expired_leases</Text>
              </Row>
              <Row gap={8}>
                <Pill tone="success" size="sm">
                  Retry
                </Pill>
                <Text>FAILED only → READY, same input_json, bump attempt_no</Text>
              </Row>
              <Row gap={8}>
                <Pill size="sm">New instance</Pill>
                <Text>Wrong knobs / URI — do not Retry</Text>
              </Row>
              <Row gap={8}>
                <Pill tone="deleted" size="sm">
                  Stop task
                </Pill>
                <Text>RUNNING + can_stop → sp_stop_node</Text>
              </Row>
              <Row gap={8}>
                <Pill tone="deleted" size="sm">
                  Fail queued
                </Pill>
                <Text>READY/PENDING → sp_fail_node (4098)</Text>
              </Row>
              <Row gap={8}>
                <Pill tone="deleted" size="sm">
                  Cancel/fail run
                </Pill>
                <Text>Drain queue + stop later-stage continue: sp_cancel_instance / sp_fail_instance</Text>
              </Row>
              <Text tone="secondary" size="small">
                No status dropdown. No forceRerun on FAILED (no CAAS success to skip).
                Instance pause stays deferred (can_pause is almost always false).
              </Text>
            </Stack>
          </CardBody>
        </Card>
      </Grid>

      <H2>Platform SamplePrep Guardrails</H2>
      <Text tone="secondary">
        Two wf.data_type documents. Site persists the full published window.
        Profile, procedure, and study persist a sparse overlay. Study GET keeps
        schema_id study_action_config_overlay so existing wiring does not break.
        The study grid must not POST to shared layers.
      </Text>
      <Table
        striped
        headers={["Screen", "schema_id", "Proc", "Persist"]}
        rows={[
          [
            "Platform → Site → Guardrails",
            "sample_prep_guardrails",
            "sp_get/set_site_guardrails_editor",
            "Full QC slice; reject partial window",
          ],
          [
            "Platform → Profile → Guardrails",
            "sample_prep_guardrails_overlay",
            "sp_get/set_profile_guardrails_editor",
            "Sparse vs site; upsert draft then publish",
          ],
          [
            "Platform → Procedure → Guardrails",
            "sample_prep_guardrails_overlay",
            "sp_get/set_assay_procedure_guardrails_editor",
            "Sparse vs site+profile; upsert draft then publish",
          ],
          [
            "Studies → Guardrails (next run)",
            "study_action_config_overlay",
            "sp_get/set_study_guardrails_editor",
            "Sparse vs inherited; study row only",
          ],
        ]}
        rowTone={["info", undefined, undefined, "success"]}
      />
      <Text tone="tertiary" size="small">
        RBAC: system administrator (site), platform admin (packs), study lead
        (study overlay). Caption + deep-link inherited layers. Analyte
        fill-missing stays at instance bake, not in SQL GET.
      </Text>

      <H2>Missing FASTQ</H2>
      <Callout tone="warning" title="Same URI, then Retry">
        sample.download_fastq fails when the object is not at the baked source URI.
        Lab places the file on that fastqSource path. Task detail shows source_uri.
        Operator confirms and clicks Retry. Next claim uses the same payload.
      </Callout>

      <H2>Schema swimlanes</H2>
      <Table
        striped
        headers={["Schema", "Owns", "UI label caution"]}
        rows={[
          ["portal", "Samples, LabSamples, Role2Node", "Customer cohorts ≠ study arms"],
          ["cfg", "study_group, storage, packs, study_instance_link", "Study arms"],
          ["wf", "graphs, instances, node_execution, leases", "Execution only"],
          ["RBAC", "Users, grants, scopes, sessions", "User groups"],
          ["Contract", "terms, scopes, pack entitlements, quotas", "Admin only"],
        ]}
      />

      <H2>System administrator</H2>
      <Callout tone="neutral" title="Clusters, workers, and deployment">
        Platform → Clusters & workers. Fleet desired_state is not the /work map.
        s3://goliath/samples/ (path-style /samples/goliath) is a published
        archive endpoint on the Deployment screen — not a Studies nav leaf.
        Operators only select redacted endpoints.
      </Callout>
      <Table
        striped
        headers={["Role", "Path / URI", "Screen"]}
        rows={[
          ["Cluster share", "/work (worker_mount_path)", "Clusters"],
          ["Release", "/work/goliath/current", "Deployment"],
          ["Sample scratch", "/work/samples/{id}/", "Deployment"],
          ["Study outputs", "/work/projects/<study>/", "Deployment"],
          ["Lab ingress", "published fastqSource", "Storage authoring"],
          ["Sample / H5 archive", "published sampleDestination", "Deployment"],
        ]}
      />

      <H2>Admin</H2>
      <Grid columns={2} gap={16}>
        <Stack gap={8}>
          <H3>RBAC</H3>
          <Text tone="secondary">
            New screens call portal.sp_* wrappers. Login nav still uses
            RBAC.spGetUserNavTree. Do not call RBAC write procs from EpiPortal.
          </Text>
          <Table
            headers={["Screen", "Proc"]}
            rows={[
              ["Users", "sp_list/get/upsert_user"],
              ["Identities", "sp_list_user_identities"],
              ["Grants", "sp_grant/revoke_user_role"],
              ["User groups", "sp_set_user_group_members/roles"],
              ["Nav", "sp_grant/deny_role_nav_node"],
              ["Invites", "sp_create/list/revoke_invitation"],
            ]}
          />
        </Stack>
        <Stack gap={8}>
          <H3>Contracts</H3>
          <Text tone="secondary">
            Commercial grain is process pack (methylation | rnaseq | proteomics),
            not workflow_def ids. Graph entitlements stay as derived quotas.
          </Text>
          <Table
            headers={["Pack", "Start wizard"]}
            rows={[
              ["Entitled", "Shown in *_catalog when @scope_id set"],
              ["Not entitled", "Hidden — no disabled tease"],
              ["scope_id NULL", "Unfiltered (dev / CI)"],
              ["Start", "PROCESS_PACK_NOT_ENTITLED if mismatch"],
            ]}
            rowTone={["success", "danger", "info", "warning"]}
          />
        </Stack>
      </Grid>

      <Divider />

      <H2>SQL shipped in this plan</H2>
      <Table
        striped
        stickyHeader
        headers={["Area", "Objects", "Deploy"]}
        rows={[
          [
            "Study pipeline",
            "sp_list_study_instances, sp_get_study_pipeline_progress, wf.pipeline_stage_map",
            "portal_study_pipeline_api.sql",
          ],
          [
            "Monitor / retry / cancel",
            "header, sample progress, config snapshot, retry, fail/stop node, cancel/fail instance",
            "portal_ops_recovery_api.sql + portal_study_ops_api.sql",
          ],
          [
            "Layered Guardrails editors",
            "site/profile/procedure GET/SET + pack upsert/publish",
            "portal_guardrails_editor.sql + cfg_process_pack_catalog.sql",
          ],
          [
            "RBAC admin",
            "users, grants, groups, scopes, sessions, Role2Node, invitations, BypassScope, session revoke",
            "portal_rbac_api.sql",
          ],
          [
            "Contract packs",
            "process packs + set scopes/limits/role policies; Start study_row_id link",
            "portal_contract_api.sql + portal_study_ops_api.sql",
          ],
        ]}
      />

      <Text tone="tertiary" size="small">
        MSSQL + PostgreSQL twins. Register in workflow_engine/contract/db_objects.yaml.
        Remaining UI work is EpiPortal FrameKeys / NavTree in the other repo.
      </Text>
    </Stack>
  );
}
