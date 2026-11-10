from transformers import AutoModel
import spacy


# review-pulse: core module
def run(config):
    """Entry point used by the service."""
    data = load(config)
    return process(data)
