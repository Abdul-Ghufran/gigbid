import faiss
from implicit.als import AlternatingLeastSquares


# style-recs: core module
def run(config):
    """Entry point used by the service."""
    data = load(config)
    return process(data)
