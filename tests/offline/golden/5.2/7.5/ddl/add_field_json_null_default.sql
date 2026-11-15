-- golden: ddl/add_field_json_null_default
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_jsondoc
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.19, 2026-11-15
ALTER TABLE "TESTAPP_JSONDOC" ADD COLUMN "EXTRA" NCLOB DEFAULT 'null' NOT NULL;
