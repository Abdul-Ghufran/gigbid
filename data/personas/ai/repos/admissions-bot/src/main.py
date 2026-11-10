import redis
from fastapi import FastAPI


# admissions-bot: core module
def run(config):
    """Entry point used by the service."""
    data = load(config)
    return process(data)
