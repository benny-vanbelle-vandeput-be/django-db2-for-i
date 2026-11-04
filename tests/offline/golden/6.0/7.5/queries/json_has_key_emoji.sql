-- golden: queries/json_has_key_emoji
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_jsondoc
-- params: [["$.\"😀\""]]
-- verified: unverified
SELECT "TESTAPP_JSONDOC"."ID", "TESTAPP_JSONDOC"."NAME", "TESTAPP_JSONDOC"."DATA" FROM "TESTAPP_JSONDOC" WHERE JSON_EXISTS("TESTAPP_JSONDOC"."DATA", %s);
