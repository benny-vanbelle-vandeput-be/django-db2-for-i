-- golden: queries/json_in_values
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_jsondoc
-- params: [["7", "true"]]
-- verified: unverified
SELECT "TESTAPP_JSONDOC"."ID", "TESTAPP_JSONDOC"."NAME", "TESTAPP_JSONDOC"."DATA" FROM "TESTAPP_JSONDOC" WHERE JSON_QUERY(('[' CONCAT "TESTAPP_JSONDOC"."DATA" CONCAT ']'), '$[0]') IN (JSON_QUERY(JSON_OBJECT('value' VALUE CAST(%s AS NVARCHAR(32)) FORMAT JSON), '$.value'), JSON_QUERY(JSON_OBJECT('value' VALUE CAST(%s AS NVARCHAR(32)) FORMAT JSON), '$.value'));
