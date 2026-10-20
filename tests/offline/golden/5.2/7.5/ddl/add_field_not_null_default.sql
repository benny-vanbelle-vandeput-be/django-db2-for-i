-- golden: ddl/add_field_not_null_default
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_defaults
-- params: [[], []]
-- verified: unverified
ALTER TABLE "TESTAPP_DEFAULTS" ADD COLUMN "NICKNAME" NVARCHAR(20) DEFAULT UX'004F00270042007200690065006E' NOT NULL;
ALTER TABLE "TESTAPP_DEFAULTS" ALTER COLUMN "NICKNAME" DROP DEFAULT;
