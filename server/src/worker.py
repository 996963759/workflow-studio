from .jobs import RunJobQueue, RunJobWorker
from .logging_config import configure_logging
from .storage import default_store


def main() -> None:
    configure_logging()
    queue = RunJobQueue(default_store)
    worker = RunJobWorker(queue)
    worker.run_forever()


if __name__ == "__main__":
    main()
