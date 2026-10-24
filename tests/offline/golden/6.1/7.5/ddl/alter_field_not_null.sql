-- golden: ddl/alter_field_not_null
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_defaults
-- params: [[], []]
-- verified: unverified
UPDATE "TESTAPP_DEFAULTS" SET "NUMBER" = -1 WHERE "NUMBER" IS NULL;
ALTER TABLE "TESTAPP_DEFAULTS" ALTER COLUMN "NUMBER" SET NOT NULL;
