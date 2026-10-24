The Django test runs on IBM i and the offline query corpus use Django's own
`DEFAULT_AUTO_FIELD` per version (`AutoField` on 5.2, `BigAutoField` from
6.0 on) instead of `AutoField` everywhere, as Django's reference settings do.
