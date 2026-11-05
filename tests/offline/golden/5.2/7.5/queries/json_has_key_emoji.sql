-- golden: queries/json_has_key_emoji
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_jsondoc
-- params: [["$.\"😀\""]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.19, 2026-11-05
SELECT "TESTAPP_JSONDOC"."ID", "TESTAPP_JSONDOC"."NAME", "TESTAPP_JSONDOC"."DATA" FROM "TESTAPP_JSONDOC" WHERE JSON_EXISTS("TESTAPP_JSONDOC"."DATA", %s);
