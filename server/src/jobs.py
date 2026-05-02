import logging
import time
from concurrent.futures import ThreadPoolExecutor

try:
    from redis import Redis
    from redis.exceptions import RedisError
except ImportError:  # pragma: no cover - local SQLite tests do not need Redis.
    Redis = None  # type: ignore[assignment]

    class RedisError(Exception):
        pass

from .config import (
    REDIS_RUN_JOB_QUEUE,
    REDIS_URL,
    RUN_JOB_POLL_INTERVAL_SECONDS,
    RUN_JOB_QUEUE_BACKEND,
    RUN_JOB_WORKERS,
)
from .models import RunJobRecord
from .runner import simulate_run
from .storage import WorkflowStore


logger = logging.getLogger("workflow_studio.jobs")
executor = ThreadPoolExecutor(max_workers=RUN_JOB_WORKERS, thread_name_prefix="workflow-run")


class RunJobQueue:
    def __init__(
        self,
        store: WorkflowStore,
        backend: str = RUN_JOB_QUEUE_BACKEND,
        redis_url: str = REDIS_URL,
        redis_queue: str = REDIS_RUN_JOB_QUEUE,
    ) -> None:
        self.store = store
        self.backend = backend
        self.redis_queue = redis_queue
        self.redis_client = self._create_redis_client(redis_url) if backend == "redis" else None

    def _create_redis_client(self, redis_url: str):
        if Redis is None:
            logger.warning("redis package is not installed; falling back to database queue")
            self.backend = "database"
            return None
        return Redis.from_url(redis_url, decode_responses=True)

    def enqueue(self, user_id: str, workspace_id: str, workflow_id: str, input_text: str) -> RunJobRecord:
        job = self.store.create_run_job(user_id, workspace_id, workflow_id, input_text)
        if self.backend == "thread":
            executor.submit(self.run_job_by_id, job.id)
        elif self.backend == "redis":
            try:
                self.redis_client.lpush(self.redis_queue, job.id)  # type: ignore[union-attr]
            except RedisError:
                logger.exception("failed to publish run job to redis; job stays queued job_id=%s", job.id)
        return job

    def run_job_by_id(self, job_id: str) -> bool:
        job = self.store.claim_run_job(job_id)
        if not job:
            return False
        self._run_claimed_job(job)
        return True

    def run_next_queued_job(self) -> bool:
        job = self.store.claim_run_job()
        if not job:
            return False
        self._run_claimed_job(job)
        return True

    def _run_claimed_job(self, job: RunJobRecord) -> None:
        try:
            workflow = self.store.get_workflow_for_job(job.workflow_id, job.id)
            if not workflow:
                raise RuntimeError("Workflow not found")
            user_id = self.store.get_run_job_user_id(job.id)
            workspace_id = self.store.get_run_job_workspace_id(job.id)
            model_configs = {}
            deepseek_config = self.store.get_runtime_model_config_for_job(job.id, "deepseek")
            if deepseek_config:
                model_configs["deepseek"] = deepseek_config
            aliyun_config = self.store.get_runtime_model_config_for_job(job.id, "aliyun")
            if aliyun_config:
                model_configs["aliyun"] = aliyun_config
            response = simulate_run(
                workflow,
                job.input_text,
                user_id,
                workspace_id,
                model_configs,
            )
            run = self.store.create_run_for_job(job.id, workflow.id, workflow.name, job.input_text, response)
            self.store.update_run_job(job.id, "succeeded", run_id=run.id)
        except Exception as error:  # noqa: BLE001 - stored as job error for the UI.
            logger.exception("run job failed job_id=%s", job.id)
            self.store.update_run_job(job.id, "failed", error=str(error))


class RunJobWorker:
    def __init__(
        self,
        queue: RunJobQueue,
        poll_interval_seconds: float = RUN_JOB_POLL_INTERVAL_SECONDS,
    ) -> None:
        self.queue = queue
        self.poll_interval_seconds = poll_interval_seconds

    def recover_interrupted_jobs(self) -> int:
        count = self.queue.store.requeue_interrupted_run_jobs()
        if count:
            logger.warning("requeued interrupted run jobs count=%s", count)
        return count

    def run_forever(self) -> None:
        self.recover_interrupted_jobs()
        logger.info("run job worker started backend=%s", self.queue.backend)
        while True:
            ran = self._run_once()
            if not ran:
                time.sleep(self.poll_interval_seconds)

    def _run_once(self) -> bool:
        if self.queue.backend == "redis" and self.queue.redis_client is not None:
            try:
                item = self.queue.redis_client.brpop(self.queue.redis_queue, timeout=2)
            except RedisError:
                logger.exception("redis dequeue failed; falling back to database polling once")
                return self.queue.run_next_queued_job()
            if not item:
                return self.queue.run_next_queued_job()
            _, job_id = item
            return self.queue.run_job_by_id(job_id)
        return self.queue.run_next_queued_job()
