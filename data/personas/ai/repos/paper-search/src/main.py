FROM python:
import faiss


# paper-search: core module
def run(config):
    """Entry point used by the service."""
    data = load(config)
    return process(data)
