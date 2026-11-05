-- golden: queries/json_values_key
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_jsondoc
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.19, 2026-11-05
SELECT JSON_QUERY("TESTAPP_JSONDOC"."DATA", '$."tags"[1]') AS "DATA__TAGS__1" FROM "TESTAPP_JSONDOC" ORDER BY JSON_QUERY("TESTAPP_JSONDOC"."DATA", '$."n"') ASC;
