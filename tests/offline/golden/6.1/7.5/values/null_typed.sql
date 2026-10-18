-- golden: values/null_typed
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[]]
-- verified: IBM i 7.5 on PUB400, 2026-10-18
SELECT CAST(NULL AS INTEGER) AS "X" FROM "TESTAPP_AUTHOR";
