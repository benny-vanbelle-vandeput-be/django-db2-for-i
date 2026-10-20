-- golden: values/date
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[{"$date": "2026-10-17"}]]
-- verified: unverified
SELECT CAST(%s AS DATE) AS "X" FROM "TESTAPP_AUTHOR";
