-- golden: queries/json_key_in_json_null
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_jsondoc
-- params: [["3"]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.3, 2026-11-15
SELECT "TESTAPP_JSONDOC"."ID", "TESTAPP_JSONDOC"."NAME", "TESTAPP_JSONDOC"."DATA" FROM "TESTAPP_JSONDOC" WHERE (JSON_QUERY("TESTAPP_JSONDOC"."DATA", '$."n"') IN (JSON_QUERY(JSON_OBJECT('value' VALUE CAST(%s AS NVARCHAR(32)) FORMAT JSON), '$.value')) OR (CASE WHEN JSON_EXISTS("TESTAPP_JSONDOC"."DATA", '$."n"') THEN 1 END = 1 AND JSON_QUERY("TESTAPP_JSONDOC"."DATA", '$."n"') IS NULL));
