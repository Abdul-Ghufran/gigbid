---
id: web-case-09
type: case_study
project: hr-reports
date: 2024-03
client_industry: hr tech
---
# Async report generation for an HR SaaS

## The problem
Customers waited minutes for reports and often gave up.

## What I did
- Used drf to reduce operating cost.
- The solution relied on task queue; I delivered that part myself to hit the client's launch date.
- Used Redis so the system scales cleanly.
- Brought in AWS to make results reproducible.

## Outcome
The work cut report wait from 4 minutes to 12 seconds.

_Timeline: about 10 weeks. Client industry: hr tech._