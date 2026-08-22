Human: I've got a Postgres query that's suddenly taking 12 seconds. It was fine last week. Where do I even start?

Assistant: Start with `EXPLAIN (ANALYZE, BUFFERS)` on the actual query — not `EXPLAIN` alone, which only gives you the planner's guess.

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM orders WHERE customer_id = 42 ORDER BY created_at DESC LIMIT 20;
```

Three things to look for:

1. **Seq Scan where you expected an Index Scan** — usually means the planner's row estimate is off.
2. **A big gap between `rows=` estimated and `actual rows=`** — stale statistics.
3. **High `read=` counts in BUFFERS** — you're going to disk instead of cache.

If it worked last week and doesn't now, stale statistics after a bulk load is the most common cause.

Human: The estimate says 12 rows, actual is 340000. So statistics?

Assistant: Almost certainly. Run:

```sql
ANALYZE orders;
```

Then re-run the EXPLAIN. If the estimate snaps to something close to 340k, autovacuum wasn't keeping up.

Longer term, either lower the autovacuum threshold for that table:

| setting | default | suggested |
|---|---|---|
| `autovacuum_analyze_scale_factor` | 0.1 | 0.02 |
| `autovacuum_analyze_threshold` | 50 | 50 |

or add an explicit `ANALYZE` at the end of whatever bulk-loads the table.

Human: That fixed it — 40ms now. Thanks.

Assistant: Nice. Worth adding a check to your load job so this doesn't come back: if the loader inserts more than a few percent of the table, have it run `ANALYZE` before it exits.
