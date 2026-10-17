-- golden: ddl/create_tag
-- django: 6.1
-- profile: 7.5
-- depends: -
-- params: [[]]
-- verified: IBM i 7.5 on PUB400, 2026-10-17
CREATE TABLE "TESTAPP_TAG" ("ID" CHAR(32) NOT NULL PRIMARY KEY, "LABEL" NVARCHAR(50) NOT NULL UNIQUE);
