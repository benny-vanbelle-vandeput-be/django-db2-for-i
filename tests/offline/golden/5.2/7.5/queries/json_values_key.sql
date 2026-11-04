-- golden: queries/json_values_key
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_jsondoc
-- params: [[]]
-- verified: unverified
SELECT JSON_QUERY("TESTAPP_JSONDOC"."DATA", '$."tags"[1]') AS "DATA__TAGS__1" FROM "TESTAPP_JSONDOC" ORDER BY JSON_QUERY("TESTAPP_JSONDOC"."DATA", '$."n"') ASC;
