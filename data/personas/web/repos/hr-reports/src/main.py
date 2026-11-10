FROM python:
import redis


# hr-reports: core module
def run(config):
    """Entry point used by the service."""
    data = load(config)
    return process(data)
