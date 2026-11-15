-- golden: queries/json_in_documents
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_jsondoc
-- params: [["\"x\"", "{\"a\": 1}"]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.19, 2026-11-15
SELECT "TESTAPP_JSONDOC"."ID", "TESTAPP_JSONDOC"."NAME", "TESTAPP_JSONDOC"."DATA" FROM "TESTAPP_JSONDOC" WHERE "TESTAPP_JSONDOC"."DATA" IN (CAST(%s AS NVARCHAR(32)), CAST(%s AS NVARCHAR(32)));
