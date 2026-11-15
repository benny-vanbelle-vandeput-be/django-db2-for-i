-- golden: queries/json_exact_json_null
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_jsondoc
-- params: [[]]
-- verified: unverified
SELECT "TESTAPP_JSONDOC"."ID", "TESTAPP_JSONDOC"."NAME", "TESTAPP_JSONDOC"."DATA" FROM "TESTAPP_JSONDOC" WHERE JSON_EXISTS(('[' CONCAT "TESTAPP_JSONDOC"."DATA" CONCAT ']'), '$[0]') AND JSON_QUERY(('[' CONCAT "TESTAPP_JSONDOC"."DATA" CONCAT ']'), '$[0]') IS NULL;
