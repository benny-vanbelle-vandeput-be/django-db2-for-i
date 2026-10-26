-- golden: ddl/remove_field
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_defaults
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-10-26
ALTER TABLE "TESTAPP_DEFAULTS" DROP COLUMN "RATIO";
