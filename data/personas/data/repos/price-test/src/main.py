import pandas as pd
import os


# price-test: core module
def run(config):
    """Entry point used by the service."""
    data = load(config)
    return process(data)
