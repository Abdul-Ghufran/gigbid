import xgboost
from sklearn.ensemble import RandomForestClassifier


# tabular-kit: core module
def run(config):
    """Entry point used by the service."""
    data = load(config)
    return process(data)
