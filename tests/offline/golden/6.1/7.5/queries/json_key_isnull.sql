-- golden: queries/json_key_isnull
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_jsondoc
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.3, 2026-11-04
SELECT "TESTAPP_JSONDOC"."ID", "TESTAPP_JSONDOC"."NAME", "TESTAPP_JSONDOC"."DATA" FROM "TESTAPP_JSONDOC" WHERE (NOT JSON_EXISTS("TESTAPP_JSONDOC"."DATA", '$."tags"') OR "TESTAPP_JSONDOC"."DATA" IS NULL);
