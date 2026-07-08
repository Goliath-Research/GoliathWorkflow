import { Divider, Grid, H1, H2, Stack, Stat, Table, Text } from 'cursor/canvas';

export default function MethylPipelineDbRunbook() {
  return (
    <Stack gap={20}>
      <H1>MethylPipeline Database Runbook</H1>
      <Text>
        A quick operational guide for setting up and validating the database layer used by this
        workspace.
      </Text>

      <Grid columns={3} gap={16}>
        <Stat value="1" label="Primary DB Script" />
        <Stat value=".venv" label="Required Python Env" />
        <Stat value="2" label="Core Validation Steps" />
      </Grid>

      <Divider />

      <H2>Primary Artifact</H2>
      <Table
        headers={['Item', 'Path', 'Why It Matters']}
        rows={[
          [
            'Schema / DB setup script',
            'workflow_engine/MethylPipelineDB_Script.sql',
            'Defines the database objects and baseline structure used by the pipeline.',
          ],
        ]}
      />

      <Divider />

      <H2>Recommended Execution Sequence</H2>
      <Table
        headers={['Step', 'Command', 'Expected Outcome']}
        rows={[
          [
            'Activate environment',
            'source .venv/bin/activate',
            'Project Python dependencies are available for pipeline tooling.',
          ],
          [
            'Run DB initialization script',
            'Execute MethylPipelineDB_Script.sql on your target SQL server',
            'Schema objects are created or updated for pipeline use.',
          ],
          [
            'Smoke-check Python entrypoints',
            '.venv/bin/python -m pytest (or specific tests)',
            'Confirms app code can run against expected environment constraints.',
          ],
        ]}
      />

      <Divider />

      <H2>Troubleshooting Cues</H2>
      <Table
        headers={['Symptom', 'Likely Cause', 'Next Action']}
        rows={[
          [
            'Import/module errors during tests',
            'Virtual environment not active',
            'Re-run `source .venv/bin/activate` before Python commands.',
          ],
          [
            'Pipeline fails on missing DB objects',
            'DB script not applied to the current target database',
            'Reapply `MethylPipelineDB_Script.sql` and verify target DB selection.',
          ],
          [
            'Local behavior differs from teammate',
            'Different environment activation or script version',
            'Confirm `.venv` usage and align on the latest SQL script revision.',
          ],
        ]}
      />

      <Divider />

      <H2>How to Extend This Canvas</H2>
      <Text>
        Add sections for table ownership, migration history, and environment-specific differences as
        the database lifecycle evolves.
      </Text>
    </Stack>
  );
}
