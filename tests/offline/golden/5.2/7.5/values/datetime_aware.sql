-- golden: values/datetime_aware
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[{"$datetime": "2026-10-17T13:30:00.123456"}]]
-- verified: unverified
SELECT CAST(%s AS TIMESTAMP(6)) AS "X" FROM "TESTAPP_AUTHOR";
