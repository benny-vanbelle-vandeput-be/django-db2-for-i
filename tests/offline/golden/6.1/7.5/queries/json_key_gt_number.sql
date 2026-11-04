-- golden: queries/json_key_gt_number
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_jsondoc
-- params: [[10]]
-- verified: unverified
SELECT "TESTAPP_JSONDOC"."ID", "TESTAPP_JSONDOC"."NAME", "TESTAPP_JSONDOC"."DATA" FROM "TESTAPP_JSONDOC" WHERE JSON_VALUE("TESTAPP_JSONDOC"."DATA", '$."n"' RETURNING DECFLOAT(34)) > %s;
