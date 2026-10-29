-- golden: dml/insert_returning_db_defaults
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_defaults
-- params: [[5]]
-- verified: unverified
SELECT "ID", "TEXT", "FLAG", "NUMBER", "AMOUNT", "RATIO", "DAY", "CLOCK", "STAMP", "DATA", "CODE", "NOTHING" FROM FINAL TABLE (INSERT INTO "TESTAPP_DEFAULTS" ("TEXT", "FLAG", "NUMBER", "AMOUNT", "RATIO", "DAY", "CLOCK", "STAMP", "DATA", "CODE", "NOTHING") VALUES (DEFAULT, DEFAULT, %s, DEFAULT, DEFAULT, DEFAULT, DEFAULT, DEFAULT, DEFAULT, DEFAULT, DEFAULT));
