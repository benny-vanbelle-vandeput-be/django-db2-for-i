-- golden: queries/json_has_keys
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_jsondoc
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.10, 2026-11-05
SELECT "TESTAPP_JSONDOC"."ID", "TESTAPP_JSONDOC"."NAME", "TESTAPP_JSONDOC"."DATA" FROM "TESTAPP_JSONDOC" WHERE (JSON_EXISTS("TESTAPP_JSONDOC"."DATA", '$."a"') AND JSON_EXISTS("TESTAPP_JSONDOC"."DATA", '$."it''s 100%%"'));
