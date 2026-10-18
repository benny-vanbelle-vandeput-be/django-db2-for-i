-- golden: values/date
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[{"$date": "2026-10-17"}]]
-- verified: IBM i 7.5 on PUB400, 2026-10-18
SELECT CAST(%s AS DATE) AS "X" FROM "TESTAPP_AUTHOR";
