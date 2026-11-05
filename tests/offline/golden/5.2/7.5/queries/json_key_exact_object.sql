-- golden: queries/json_key_exact_object
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_jsondoc
-- params: [["{\"ok\": true}"]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.19, 2026-11-05
SELECT "TESTAPP_JSONDOC"."ID", "TESTAPP_JSONDOC"."NAME", "TESTAPP_JSONDOC"."DATA" FROM "TESTAPP_JSONDOC" WHERE JSON_QUERY("TESTAPP_JSONDOC"."DATA", '$."meta"') = JSON_QUERY(JSON_OBJECT('value' VALUE CAST(%s AS NVARCHAR(32)) FORMAT JSON), '$.value');
