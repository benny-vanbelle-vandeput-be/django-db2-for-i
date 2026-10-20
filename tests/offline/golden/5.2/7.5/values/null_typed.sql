-- golden: values/null_typed
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[]]
-- verified: unverified
SELECT CAST(NULL AS INTEGER) AS "X" FROM "TESTAPP_AUTHOR";
