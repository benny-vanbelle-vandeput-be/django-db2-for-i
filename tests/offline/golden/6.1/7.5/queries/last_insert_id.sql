-- golden: queries/last_insert_id
-- django: 6.1
-- profile: 7.5
-- depends: -
-- params: [[]]
-- verified: IBM i 7.5 on PUB400, 2026-10-17
SELECT IDENTITY_VAL_LOCAL() FROM SYSIBM.SYSDUMMY1;
