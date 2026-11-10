import pandas as pd
from airflow import DAG


# crm-etl: core module
def run(config):
    """Entry point used by the service."""
    data = load(config)
    return process(data)
