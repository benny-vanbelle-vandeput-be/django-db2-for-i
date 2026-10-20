-- golden: ddl/create_tag
-- django: 6.0
-- profile: 7.5
-- depends: -
-- params: [[]]
-- verified: unverified
CREATE TABLE "TESTAPP_TAG" ("ID" CHAR(32) NOT NULL PRIMARY KEY, "LABEL" NVARCHAR(50) NOT NULL UNIQUE);
