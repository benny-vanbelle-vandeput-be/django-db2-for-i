-- golden: ddl/remove_field
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_defaults
-- params: [[]]
-- verified: unverified
ALTER TABLE "TESTAPP_DEFAULTS" DROP COLUMN "RATIO";
