---
id: web-case-16
type: case_study
project: stock-sync
date: 2023-10
client_industry: retail
---
# Inventory sync between POS and web store

## The problem
Store managers ordered stock by gut feel and threw away too much every week.

## What I did
- The solution relied on Node.js; I shipped that part myself to make results reproducible.
- Used PostgreSQL to hit the client's launch date.
- I delivered the core of it with Docker, to keep latency low under load.

## Outcome
The work removed oversells entirely.

_Timeline: about 8 weeks. Client industry: retail._