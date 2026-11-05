-- golden: queries/json_json_object
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_jsondoc
-- params: [["name", "data", "empty"]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.3, 2026-11-05
SELECT JSON_OBJECT((CAST(%s AS NVARCHAR(32))) VALUE "TESTAPP_JSONDOC"."NAME", (CAST(%s AS NVARCHAR(32))) VALUE "TESTAPP_JSONDOC"."DATA" FORMAT JSON, (CAST(%s AS NVARCHAR(32))) VALUE JSON_OBJECT(RETURNING NCLOB(1M)) FORMAT JSON RETURNING NCLOB(1M)) AS "X" FROM "TESTAPP_JSONDOC";
