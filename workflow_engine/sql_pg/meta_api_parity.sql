/*
  PostgreSQL parity for Meta.sp* / Meta.fn* procedures extracted from
  workflow_engine/sql_mssql/meta_api.sql.

  Most Meta procedures depend on the MSSQL system-catalogue (sys.columns,
  sys.tables, sp_executesql dynamic SQL for table/view DDL).  These cannot be
  faithfully ported to PG without re-implementing the same catalogue-driven DDL
  in PL/pgSQL using pg_catalog views.  The DDL-generation procs (spClassAdded,
  spClassCreateTableSql, spClassCreateViewSql, spClassCreateHistorySql) are
  stubbed.  The data-manipulation procs (spInsertObject, spUpdateObject,
  spObjectInsert, spHistoryInsert) and utility functions are fully ported using
  PG information_schema equivalents.

  Depends on:
    meta_schema.sql  – "Meta"."Classes", "Meta"."CollectionItem",
                        "Meta"."CollectionItemValue", "Meta"."Collections"
                        (schema created by meta_schema.sql)
*/

-- ──────────────────────────────────────────────────────────────────────────────
-- Utility functions
-- ──────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION "Meta".fngetviewname(p_table_name text)
RETURNS text LANGUAGE sql IMMUTABLE AS $$
  SELECT 'V' || p_table_name;
$$;

CREATE OR REPLACE FUNCTION "Meta".getclasshashistory(p_class_id int)
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT "HasHistory" FROM "Meta"."Classes" WHERE "ID" = p_class_id;
$$;

CREATE OR REPLACE FUNCTION "Meta".fngetfirstchildclassid(p_class_id int)
RETURNS int LANGUAGE sql STABLE AS $$
  SELECT MIN("ID") FROM "Meta"."Classes" WHERE "ParentID" = p_class_id;
$$;

-- fnGetClassFields: returns comma-joined column names for a class table (PG info_schema).
CREATE OR REPLACE FUNCTION "Meta".fngetclassfields(p_class_id int)
RETURNS text LANGUAGE sql STABLE AS $$
  SELECT string_agg(c.column_name, ', ' ORDER BY c.ordinal_position)
  FROM information_schema.columns c
  JOIN "Meta"."Classes" cls ON cls."TableName" = c.table_name
  WHERE cls."ID" = p_class_id
    AND c.table_schema = 'Meta';
$$;

-- fnGetClassFieldsWithTypes: column declarations (name type [NOT NULL]) for class table.
CREATE OR REPLACE FUNCTION "Meta".fngetclassfieldswithtypes(p_class_id int)
RETURNS text LANGUAGE sql STABLE AS $$
  SELECT string_agg(
    quote_ident(c.column_name) || ' ' || c.udt_name ||
    CASE
      WHEN c.character_maximum_length IS NOT NULL
        THEN '(' || c.character_maximum_length || ')'
      WHEN c.udt_name IN ('numeric','decimal')
        THEN '(' || c.numeric_precision || ',' || c.numeric_scale || ')'
      ELSE ''
    END ||
    CASE WHEN c.is_nullable = 'NO' THEN ' NOT NULL' ELSE '' END,
    E',\n' ORDER BY c.ordinal_position
  )
  FROM information_schema.columns c
  JOIN "Meta"."Classes" cls ON cls."TableName" = c.table_name
  WHERE cls."ID" = p_class_id
    AND c.table_schema = 'Meta';
$$;

-- fnGetCollectionItemAttr – retrieve a named attribute value from CollectionItemValue.
CREATE OR REPLACE FUNCTION "Meta".fngetcollectionitemattr(
  p_item_id int,
  p_attr_name text
)
RETURNS text LANGUAGE sql STABLE AS $$
  SELECT COALESCE(
    civ."ValueString",
    civ."ValueNumber"::text,
    civ."ValueDate"::text,
    civ."ValueBit"::text
  )
  FROM "Meta"."CollectionItemValue" civ
  WHERE civ."CollectionItemID" = p_item_id AND civ."Name" = p_attr_name
  LIMIT 1;
$$;

-- fnResolveCollectionItem
CREATE OR REPLACE FUNCTION "Meta".fnresolvecollectionitem(
  p_collection_name text,
  p_value text
)
RETURNS int LANGUAGE sql STABLE AS $$
  SELECT ci."ID"
  FROM "Meta"."CollectionItem" ci
  JOIN "Meta"."Collections" col ON col."ID" = ci."CollectionID"
  WHERE col."Name" = p_collection_name
    AND ci."ValueString" = p_value
  LIMIT 1;
$$;

-- fnResolveCollectionLabel
CREATE OR REPLACE FUNCTION "Meta".fnresolvecollectionlabel(
  p_collection_name text,
  p_item_id int
)
RETURNS text LANGUAGE sql STABLE AS $$
  SELECT ci."ValueString"::text
  FROM "Meta"."CollectionItem" ci
  JOIN "Meta"."Collections" col ON col."ID" = ci."CollectionID"
  WHERE col."Name" = p_collection_name AND ci."ID" = p_item_id
  LIMIT 1;
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- spHistoryInsert
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION "Meta".sphistoryinsert(
  p_obj_id int,
  p_event_id smallint
)
RETURNS TABLE(history_id bigint)
LANGUAGE plpgsql AS $$
DECLARE v_id bigint;
BEGIN
  -- meta.History table must exist (meta_schema.sql). Skip gracefully if absent.
  BEGIN
    INSERT INTO "Meta"."History" ("ObjID", "EventID")
    VALUES (p_obj_id, p_event_id)
    RETURNING "ID" INTO v_id;
  EXCEPTION WHEN undefined_table THEN
    v_id := NULL;
  END;
  RETURN QUERY SELECT v_id;
END;
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- spObjectInsert  (lightweight; creates an Objs row and returns its ID)
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION "Meta".spobjectinsert(
  p_class_id int
)
RETURNS TABLE(new_id int)
LANGUAGE plpgsql AS $$
DECLARE v_id int;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM "Meta"."Classes" WHERE "ID" = p_class_id) THEN
    RETURN;
  END IF;
  INSERT INTO "Meta"."Objs" ("ClassID") VALUES (p_class_id)
  RETURNING "ID" INTO v_id;
  RETURN QUERY SELECT v_id;
END;
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- spInsertObject  – dynamic multi-table insert via information_schema.
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION "Meta".spinsertobject(
  p_class_id int,
  p_values_json jsonb
)
RETURNS TABLE(new_id int)
LANGUAGE plpgsql AS $$
DECLARE
  v_new_id   int;
  v_table    text;
  v_cols     text;
  v_vals     text;
  v_sql      text;
  r          record;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM "Meta"."Classes" WHERE "ID" = p_class_id) THEN
    RAISE EXCEPTION 'Class ID % not found.', p_class_id;
  END IF;

  -- Create Objs row
  INSERT INTO "Meta"."Objs" ("ClassID") VALUES (p_class_id)
  RETURNING "ID" INTO v_new_id;

  -- Walk the inheritance chain leaf → root
  FOR r IN
    WITH RECURSIVE hier AS (
      SELECT "ID", COALESCE("TableName", "Name") AS tname, "ParentID", 0 AS lvl
      FROM "Meta"."Classes" WHERE "ID" = p_class_id
      UNION ALL
      SELECT c."ID", COALESCE(c."TableName", c."Name"), c."ParentID", h.lvl + 1
      FROM "Meta"."Classes" c JOIN hier h ON c."ID" = h."ParentID"
    )
    SELECT tname AS table_name FROM hier WHERE tname <> 'Objs' ORDER BY lvl DESC
  LOOP
    v_table := r.table_name;
    -- Build columns/values from JSON keys that match actual columns
    SELECT
      string_agg(quote_ident(c.column_name), ', ' ORDER BY c.ordinal_position),
      string_agg('($1->>' || quote_literal(c.column_name) || ')::' || c.udt_name, ', ' ORDER BY c.ordinal_position)
    INTO v_cols, v_vals
    FROM information_schema.columns c
    WHERE c.table_schema = 'Meta' AND c.table_name = v_table
      AND c.column_name <> 'ID'
      AND p_values_json ? c.column_name;

    IF v_cols IS NOT NULL THEN
      v_sql := format(
        'INSERT INTO "Meta".%I ("ID", %s) VALUES ($2, %s) ON CONFLICT ("ID") DO UPDATE SET (%s) = (%s)',
        v_table, v_cols, v_vals, v_cols, v_vals
      );
      EXECUTE v_sql USING p_values_json, v_new_id;
    END IF;
  END LOOP;

  -- History
  IF (SELECT "HasHistory" FROM "Meta"."Classes" WHERE "ID" = p_class_id) THEN
    PERFORM "Meta".sphistoryinsert(v_new_id, 1);
  END IF;

  RETURN QUERY SELECT v_new_id;
END;
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- spUpdateObject
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION "Meta".spupdateobject(
  p_class_id int,
  p_id int,
  p_values_json jsonb
)
RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
  v_sql   text;
  v_set   text;
  r       record;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM "Meta"."Objs" WHERE "ID" = p_id) THEN
    RAISE EXCEPTION 'Object % does not exist.', p_id;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM "Meta"."Classes" WHERE "ID" = p_class_id) THEN
    RAISE EXCEPTION 'Class ID % does not exist.', p_class_id;
  END IF;

  FOR r IN
    WITH RECURSIVE hier AS (
      SELECT "ID", COALESCE("TableName", "Name") AS tname, "ParentID", 0 AS lvl
      FROM "Meta"."Classes" WHERE "ID" = p_class_id
      UNION ALL
      SELECT c."ID", COALESCE(c."TableName", c."Name"), c."ParentID", h.lvl + 1
      FROM "Meta"."Classes" c JOIN hier h ON c."ID" = h."ParentID"
    )
    SELECT tname AS table_name FROM hier WHERE tname <> 'Objs' ORDER BY lvl DESC
  LOOP
    SELECT string_agg(
      quote_ident(c.column_name) || ' = ($1->>' || quote_literal(c.column_name) || ')::' || c.udt_name,
      ', ' ORDER BY c.ordinal_position
    )
    INTO v_set
    FROM information_schema.columns c
    WHERE c.table_schema = 'Meta' AND c.table_name = r.table_name
      AND c.column_name <> 'ID'
      AND p_values_json ? c.column_name;

    IF v_set IS NOT NULL THEN
      v_sql := format('UPDATE "Meta".%I SET %s WHERE "ID" = $2', r.table_name, v_set);
      EXECUTE v_sql USING p_values_json, p_id;
    END IF;
  END LOOP;

  IF (SELECT "HasHistory" FROM "Meta"."Classes" WHERE "ID" = p_class_id) THEN
    PERFORM "Meta".sphistoryinsert(p_id, 2);
  END IF;
END;
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- spClassDelete  (cascade delete child classes, then Objs rows)
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION "Meta".spclassdelete(p_class_id int)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE v_child_id int;
BEGIN
  IF p_class_id IS NULL THEN RETURN; END IF;
  LOOP
    v_child_id := "Meta".fngetfirstchildclassid(p_class_id);
    EXIT WHEN v_child_id IS NULL;
    PERFORM "Meta".spclassdelete(v_child_id);
  END LOOP;
END;
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- DDL-generation stubs (require MSSQL sys.columns; no faithful PG equivalent)
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION "Meta".spclasscreatetablesql(p_class_id int)
RETURNS text LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'not ported: meta.spClassCreateTableSql depends on MSSQL sys.columns DDL generation.';
END;
$$;

CREATE OR REPLACE FUNCTION "Meta".spclasscreateviewsql(p_class_id int)
RETURNS text LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'not ported: meta.spClassCreateViewSql depends on MSSQL sys.columns DDL generation.';
END;
$$;

CREATE OR REPLACE FUNCTION "Meta".spclasscreatehistorysql(p_class_id int)
RETURNS text LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'not ported: meta.spClassCreateHistorySql depends on MSSQL sys.columns DDL generation.';
END;
$$;

CREATE OR REPLACE FUNCTION "Meta".spclassadded(p_class_id int)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'not ported: meta.spClassAdded depends on DDL-generation procs (MSSQL-only).';
END;
$$;
