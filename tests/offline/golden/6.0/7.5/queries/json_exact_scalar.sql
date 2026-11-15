-- golden: queries/json_exact_scalar
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_jsondoc
-- params: [["42"]]
-- verified: unverified
SELECT "TESTAPP_JSONDOC"."ID", "TESTAPP_JSONDOC"."NAME", "TESTAPP_JSONDOC"."DATA" FROM "TESTAPP_JSONDOC" WHERE JSON_QUERY(('[' CONCAT "TESTAPP_JSONDOC"."DATA" CONCAT ']'), '$[0]') = JSON_QUERY(JSON_OBJECT('value' VALUE CAST(%s AS NVARCHAR(32)) FORMAT JSON), '$.value');
