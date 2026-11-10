from google.cloud import bigquery
SELECT 


# funnel-dive: core module
def run(config):
    """Entry point used by the service."""
    data = load(config)
    return process(data)
