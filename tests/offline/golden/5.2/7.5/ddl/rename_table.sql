-- golden: ddl/rename_table
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_switch
-- params: [[], []]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.18, 2026-10-24
RENAME TABLE "TESTAPP_SWITCH" TO "TESTAPP_LIGHTSWITCH";
RENAME TABLE "TESTAPP_LIGHTSWITCH" TO "TESTAPP_SWITCH";
