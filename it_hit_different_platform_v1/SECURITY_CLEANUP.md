# Security cleanup before/after this deploy

The original repository ZIP included local SQLite database files. Those files can contain user emails, password hashes, session records, and audit history and should not be committed to a public GitHub repository.

Delete these tracked files from GitHub if they exist:

- `data/ihd.sqlite3`
- `data/ihd.sqlite3-wal`
- `data/ihd.sqlite3-shm`
- `it_hit_different_platform_v1/data/ihd.sqlite3`
- `it_hit_different_platform_v1/data/ihd.sqlite3-wal`
- `it_hit_different_platform_v1/data/ihd.sqlite3-shm`

The included `.gitignore` prevents these files from being added again.

After Neon/PostgreSQL is active, reset/rotate the master password and ask any accounts that existed in the old public SQLite database to create/reset credentials.

Never commit `.env`, `DATABASE_URL`, API tokens, private keys, or passwords.
