-- golden: queries/json_in_documents
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_jsondoc
-- params: [["\"x\"", "{\"a\": 1}"]]
-- verified: unverified
SELECT "TESTAPP_JSONDOC"."ID", "TESTAPP_JSONDOC"."NAME", "TESTAPP_JSONDOC"."DATA" FROM "TESTAPP_JSONDOC" WHERE "TESTAPP_JSONDOC"."DATA" IN (CAST(%s AS NVARCHAR(32)), CAST(%s AS NVARCHAR(32)));
