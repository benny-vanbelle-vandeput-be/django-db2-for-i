-- golden: queries/json_has_keys
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_jsondoc
-- params: [[]]
-- verified: unverified
SELECT "TESTAPP_JSONDOC"."ID", "TESTAPP_JSONDOC"."NAME", "TESTAPP_JSONDOC"."DATA" FROM "TESTAPP_JSONDOC" WHERE (JSON_EXISTS("TESTAPP_JSONDOC"."DATA", '$."a"') AND JSON_EXISTS("TESTAPP_JSONDOC"."DATA", '$."it''s 100%%"'));
