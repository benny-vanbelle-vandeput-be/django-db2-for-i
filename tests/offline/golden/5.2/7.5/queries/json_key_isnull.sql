-- golden: queries/json_key_isnull
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_jsondoc
-- params: [[]]
-- verified: unverified
SELECT "TESTAPP_JSONDOC"."ID", "TESTAPP_JSONDOC"."NAME", "TESTAPP_JSONDOC"."DATA" FROM "TESTAPP_JSONDOC" WHERE (NOT JSON_EXISTS("TESTAPP_JSONDOC"."DATA", '$."tags"') OR "TESTAPP_JSONDOC"."DATA" IS NULL);
