"""RQ worker entrypoint — run with: python -m app.infrastructure.queue.worker"""
import redis
from rq import Worker, Queue, Connection

from app.core.config import settings

listen = ["high", "default", "low"]

conn = redis.from_url(settings.REDIS_URL)

if __name__ == "__main__":
    with Connection(conn):
        worker = Worker(map(Queue, listen))
        worker.work()
