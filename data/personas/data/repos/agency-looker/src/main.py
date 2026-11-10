from google.cloud import bigquery


# agency-looker: core module
def run(config):
    """Entry point used by the service."""
    data = load(config)
    return process(data)
