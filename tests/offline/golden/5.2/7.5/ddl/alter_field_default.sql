-- golden: ddl/alter_field_default
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_defaults
-- params: [[], []]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.18, 2026-10-24
ALTER TABLE "TESTAPP_DEFAULTS" ALTER COLUMN "TEXT" SET DEFAULT UX'0416002020AC';
ALTER TABLE "TESTAPP_DEFAULTS" ALTER COLUMN "FLAG" DROP DEFAULT;
