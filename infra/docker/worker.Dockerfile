FROM gigbid-python-base:latest
CMD ["arq", "worker.tasks.WorkerSettings"]
