import pandas as pd
SELECT 


# gym-churn: core module
def run(config):
    """Entry point used by the service."""
    data = load(config)
    return process(data)
