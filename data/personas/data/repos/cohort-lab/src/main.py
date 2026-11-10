from google.cloud import bigquery
import matplotlib.pyplot as plt


# cohort-lab: core module
def run(config):
    """Entry point used by the service."""
    data = load(config)
    return process(data)
