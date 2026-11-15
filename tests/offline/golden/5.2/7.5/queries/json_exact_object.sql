-- golden: queries/json_exact_object
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_jsondoc
-- params: [["{\"a\": [1, \"b\"]}"]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.19, 2026-11-15
SELECT "TESTAPP_JSONDOC"."ID", "TESTAPP_JSONDOC"."NAME", "TESTAPP_JSONDOC"."DATA" FROM "TESTAPP_JSONDOC" WHERE JSON_QUERY(('[' CONCAT "TESTAPP_JSONDOC"."DATA" CONCAT ']'), '$[0]') = JSON_QUERY(JSON_OBJECT('value' VALUE CAST(%s AS NVARCHAR(32)) FORMAT JSON), '$.value');
