-- golden: queries/json_key_gt_number
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_jsondoc
-- params: [[10]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.3, 2026-11-04
SELECT "TESTAPP_JSONDOC"."ID", "TESTAPP_JSONDOC"."NAME", "TESTAPP_JSONDOC"."DATA" FROM "TESTAPP_JSONDOC" WHERE JSON_VALUE("TESTAPP_JSONDOC"."DATA", '$."n"' RETURNING DECFLOAT(34)) > %s;
