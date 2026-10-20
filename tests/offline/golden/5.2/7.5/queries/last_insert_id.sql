-- golden: queries/last_insert_id
-- django: 5.2
-- profile: 7.5
-- depends: -
-- params: [[]]
-- verified: unverified
SELECT IDENTITY_VAL_LOCAL() FROM SYSIBM.SYSDUMMY1;
