/*
  MethylPipeline wf schema - align JSON payload columns to jsonb (PostgreSQL).
  Safe to re-run.
*/

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'wf'
      AND table_name = 'scope_variable'
      AND column_name = 'value_json'
      AND udt_name <> 'jsonb'
  ) THEN
    ALTER TABLE wf.scope_variable
      ALTER COLUMN value_json TYPE jsonb USING value_json::jsonb;
    RAISE NOTICE 'Aligned wf.scope_variable.value_json to jsonb.';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'wf'
      AND table_name = 'execution_context'
      AND column_name = 'context_value_json'
      AND udt_name <> 'jsonb'
  ) THEN
    ALTER TABLE wf.execution_context
      ALTER COLUMN context_value_json TYPE jsonb USING context_value_json::jsonb;
    RAISE NOTICE 'Aligned wf.execution_context.context_value_json to jsonb.';
  END IF;
END;
$$;
