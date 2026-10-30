-- golden: dml/bulk_insert_db_defaults
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_defaults
-- params: [[5, "set", false]]
-- verified: unverified
SELECT "ID", "TEXT", "FLAG", "NUMBER", "AMOUNT", "RATIO", "DAY", "CLOCK", "STAMP", "DATA", "CODE", "NOTHING" FROM FINAL TABLE (INSERT INTO "TESTAPP_DEFAULTS" ("TEXT", "FLAG", "NUMBER") VALUES (DEFAULT, DEFAULT, %s), (%s, %s, DEFAULT)) ORDER BY INPUT SEQUENCE;
