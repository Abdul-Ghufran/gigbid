# stock-sync

The inventory sync service for a retailer.

## Stack
- docker-compose
- PostgreSQL

## Running locally
```bash
make setup && make run
```

## Notes
Configuration lives in `config.yaml`. Secrets come from environment variables.