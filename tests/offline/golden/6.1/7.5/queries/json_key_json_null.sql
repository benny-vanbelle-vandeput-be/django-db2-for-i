-- golden: queries/json_key_json_null
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_jsondoc
-- params: [[]]
-- verified: unverified
SELECT "TESTAPP_JSONDOC"."ID", "TESTAPP_JSONDOC"."NAME", "TESTAPP_JSONDOC"."DATA" FROM "TESTAPP_JSONDOC" WHERE CASE WHEN JSON_EXISTS("TESTAPP_JSONDOC"."DATA", '$."x"') THEN 1 END = 1 AND JSON_QUERY("TESTAPP_JSONDOC"."DATA", '$."x"') IS NULL;
