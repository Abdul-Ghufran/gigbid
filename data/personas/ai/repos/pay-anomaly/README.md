# pay-anomaly

The payments anomaly detector for a PSP.

## Stack
- s3
- XGBoost

## Running locally
```bash
make setup && make run
```

## Notes
Configuration lives in `config.yaml`. Secrets come from environment variables.