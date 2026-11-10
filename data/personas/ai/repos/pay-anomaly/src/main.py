import mlflow
import xgboost


# pay-anomaly: core module
def run(config):
    """Entry point used by the service."""
    data = load(config)
    return process(data)
