---
title: Database Troubleshooting Guide
category: troubleshooting
service: postgres
environment: production
---

# Database Troubleshooting Guide

## Connection refused / OperationalError

`psycopg2.OperationalError: could not connect to server: Connection
refused` means the application couldn't reach the database host/port at
all — this is a network or process-availability problem, not a query
problem. Checklist:

1. Is the database process actually up? Check the managed instance's
   status page (Cloud SQL) or `pg_isready` against the host.
2. Is there a VPC/firewall change that just landed? Connection-refused
   errors that start suddenly and affect *all* traffic are almost always
   networking, not the database itself.
3. Check for a recent failover/maintenance window — a replica promotion
   can briefly refuse connections while it comes up as primary.

## Connection pool exhausted

"connection pool exhausted, 0 of N connections available" means the
application has more concurrent database work than its pool allows.
Causes: a slow query holding connections open longer than usual (check for
missing indexes), a connection leak (code path that acquires a connection
without releasing it, often in an exception path), or a genuine traffic
spike. Increasing pool size treats the symptom — always check for a leak
or a newly-slow query first.

## Slow queries / high latency

A query that used to take 40ms taking 3800ms is almost always: a missing
index after a schema change, a query planner choosing a bad plan after
table statistics went stale (`ANALYZE` fixes this), or lock contention from
a long-running transaction elsewhere. `EXPLAIN ANALYZE` the query before
assuming it's a resource problem.

## Replication lag

If read replicas are used for read traffic, check replication lag before
trusting reads from them during an incident — a replica serving 30-second-
stale data can look like "the write didn't happen" when it actually did.
