-- golden: ddl/add_field_json_null_default
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_jsondoc
-- params: [[]]
-- verified: unverified
ALTER TABLE "TESTAPP_JSONDOC" ADD COLUMN "EXTRA" NCLOB DEFAULT 'null' NOT NULL;
