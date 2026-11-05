-- golden: queries/json_json_object
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_jsondoc
-- params: [["name", "data", "empty"]]
-- verified: unverified
SELECT JSON_OBJECT((CAST(%s AS NVARCHAR(32))) VALUE "TESTAPP_JSONDOC"."NAME", (CAST(%s AS NVARCHAR(32))) VALUE "TESTAPP_JSONDOC"."DATA" FORMAT JSON, (CAST(%s AS NVARCHAR(32))) VALUE JSON_OBJECT(RETURNING NCLOB(1M)) FORMAT JSON RETURNING NCLOB(1M)) AS "X" FROM "TESTAPP_JSONDOC";
