from celery import Celery
import React


# gate-tix: core module
def run(config):
    """Entry point used by the service."""
    data = load(config)
    return process(data)
