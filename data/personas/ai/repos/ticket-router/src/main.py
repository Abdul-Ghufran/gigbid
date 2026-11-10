import torch
from fastapi import FastAPI


# ticket-router: core module
def run(config):
    """Entry point used by the service."""
    data = load(config)
    return process(data)
