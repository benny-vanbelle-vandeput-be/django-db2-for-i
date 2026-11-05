-- golden: queries/json_json_array
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_jsondoc
-- params: [["n"]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.10, 2026-11-05
SELECT JSON_ARRAY("TESTAPP_JSONDOC"."NAME", CAST(NULL AS NVARCHAR(32)), JSON_OBJECT((CAST(%s AS NVARCHAR(32))) VALUE "TESTAPP_JSONDOC"."NAME" RETURNING NCLOB(1M)) FORMAT JSON NULL ON NULL RETURNING NCLOB(1M)) AS "X" FROM "TESTAPP_JSONDOC";
