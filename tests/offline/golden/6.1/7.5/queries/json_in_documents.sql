-- golden: queries/json_in_documents
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_jsondoc
-- params: [["\"x\"", "{\"a\": 1}"]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.3, 2026-11-15
SELECT "TESTAPP_JSONDOC"."ID", "TESTAPP_JSONDOC"."NAME", "TESTAPP_JSONDOC"."DATA" FROM "TESTAPP_JSONDOC" WHERE JSON_QUERY(('[' CONCAT "TESTAPP_JSONDOC"."DATA" CONCAT ']'), '$[0]') IN (JSON_QUERY(JSON_OBJECT('value' VALUE CAST(%s AS NVARCHAR(32)) FORMAT JSON), '$.value'), JSON_QUERY(JSON_OBJECT('value' VALUE CAST(%s AS NVARCHAR(32)) FORMAT JSON), '$.value'));
