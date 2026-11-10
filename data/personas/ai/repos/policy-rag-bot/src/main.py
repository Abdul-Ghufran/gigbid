FROM python:
from fastapi import FastAPI


# policy-rag-bot: core module
def run(config):
    """Entry point used by the service."""
    data = load(config)
    return process(data)
