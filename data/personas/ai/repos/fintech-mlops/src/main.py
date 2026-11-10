runs-on: ubuntu-latest
import boto3


# fintech-mlops: core module
def run(config):
    """Entry point used by the service."""
    data = load(config)
    return process(data)
