-- golden: queries/last_insert_id
-- django: 5.2
-- profile: 7.5
-- depends: -
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.18, 2026-10-20
SELECT IDENTITY_VAL_LOCAL() FROM SYSIBM.SYSDUMMY1;
