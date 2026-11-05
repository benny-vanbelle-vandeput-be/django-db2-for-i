-- golden: queries/json_key_in
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_jsondoc
-- params: [["3", "\"a'b\""]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.19, 2026-11-05
SELECT "TESTAPP_JSONDOC"."ID", "TESTAPP_JSONDOC"."NAME", "TESTAPP_JSONDOC"."DATA" FROM "TESTAPP_JSONDOC" WHERE JSON_QUERY("TESTAPP_JSONDOC"."DATA", '$."n"') IN (JSON_QUERY(JSON_OBJECT('value' VALUE CAST(%s AS NVARCHAR(32)) FORMAT JSON), '$.value'), JSON_QUERY(JSON_OBJECT('value' VALUE CAST(%s AS NVARCHAR(32)) FORMAT JSON), '$.value'));
