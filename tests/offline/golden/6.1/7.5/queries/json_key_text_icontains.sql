-- golden: queries/json_key_text_icontains
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_jsondoc
-- params: [["%é%"]]
-- verified: unverified
SELECT "TESTAPP_JSONDOC"."ID", "TESTAPP_JSONDOC"."NAME", "TESTAPP_JSONDOC"."DATA" FROM "TESTAPP_JSONDOC" WHERE UPPER(JSON_QUERY("TESTAPP_JSONDOC"."DATA", '$."city"' RETURNING NCLOB(1M) OMIT QUOTES)) LIKE UPPER(%s) ESCAPE '\';
