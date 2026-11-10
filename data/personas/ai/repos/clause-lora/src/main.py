from transformers import AutoModel


# clause-lora: core module
def run(config):
    """Entry point used by the service."""
    data = load(config)
    return process(data)
