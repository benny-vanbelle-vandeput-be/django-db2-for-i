-- golden: ddl/alter_field_not_null
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_defaults
-- params: [[], []]
-- verified: unverified
UPDATE "TESTAPP_DEFAULTS" SET "NUMBER" = -1 WHERE "NUMBER" IS NULL;
ALTER TABLE "TESTAPP_DEFAULTS" ALTER COLUMN "NUMBER" SET NOT NULL;
