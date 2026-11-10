import mlflow
import pandas as pd


# telco-churn-ml: core module
def run(config):
    """Entry point used by the service."""
    data = load(config)
    return process(data)
