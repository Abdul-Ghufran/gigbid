from fastapi import FastAPI
import os


# agent-scholar: core module
def run(config):
    """Entry point used by the service."""
    data = load(config)
    return process(data)
