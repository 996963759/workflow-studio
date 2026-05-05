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

try:
    from kafka import KafkaConsumer, KafkaProducer
    from kafka.errors import KafkaError
except ImportError:  # pragma: no cover - local SQLite tests do not need Kafka.
    KafkaConsumer = None  # type: ignore[assignment]
    KafkaProducer = None  # type: ignore[assignment]

    class KafkaError(Exception):
        pass

from .config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_CONSUMER_GROUP,
    KAFKA_POLL_TIMEOUT_MS,
    KAFKA_RUN_JOB_TOPIC,
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
        kafka_bootstrap_servers: str = KAFKA_BOOTSTRAP_SERVERS,
        kafka_topic: str = KAFKA_RUN_JOB_TOPIC,
        kafka_consumer_group: str = KAFKA_CONSUMER_GROUP,
        kafka_poll_timeout_ms: int = KAFKA_POLL_TIMEOUT_MS,
    ) -> None:
        self.store = store
        self.backend = backend
        self.redis_queue = redis_queue
        self.kafka_bootstrap_servers = kafka_bootstrap_servers
        self.kafka_topic = kafka_topic
        self.kafka_consumer_group = kafka_consumer_group
        self.kafka_poll_timeout_ms = kafka_poll_timeout_ms
        self.redis_client = self._create_redis_client(redis_url) if backend == "redis" else None
        self.kafka_producer = self._create_kafka_producer(kafka_bootstrap_servers) if backend == "kafka" else None
        self.kafka_consumer = None

    def _create_redis_client(self, redis_url: str):
        if Redis is None:
            logger.warning("redis package is not installed; falling back to database queue")
            self.backend = "database"
            return None
        return Redis.from_url(redis_url, decode_responses=True)

    def _create_kafka_producer(self, bootstrap_servers: str):
        if KafkaProducer is None:
            logger.warning("kafka-python package is not installed; falling back to database queue")
            self.backend = "database"
            return None
        try:
            return KafkaProducer(
                bootstrap_servers=[server.strip() for server in bootstrap_servers.split(",") if server.strip()],
                value_serializer=lambda value: value.encode("utf-8"),
                acks="all",
            )
        except KafkaError:
            logger.exception("failed to create kafka producer; falling back to database queue")
            self.backend = "database"
            return None

    def _create_kafka_consumer(self):
        if KafkaConsumer is None:
            logger.warning("kafka-python package is not installed; falling back to database queue")
            self.backend = "database"
            return None
        return KafkaConsumer(
            self.kafka_topic,
            bootstrap_servers=[server.strip() for server in self.kafka_bootstrap_servers.split(",") if server.strip()],
            group_id=self.kafka_consumer_group,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            value_deserializer=lambda value: value.decode("utf-8"),
            consumer_timeout_ms=self.kafka_poll_timeout_ms,
        )

    def enqueue(self, user_id: str, workspace_id: str, workflow_id: str, input_text: str) -> RunJobRecord:
        job = self.store.create_run_job(user_id, workspace_id, workflow_id, input_text)
        self.publish(job.id)
        return job

    def publish(self, job_id: str) -> None:
        if self.backend == "thread":
            executor.submit(self.run_job_by_id, job_id)
        elif self.backend == "redis":
            try:
                self.redis_client.lpush(self.redis_queue, job_id)  # type: ignore[union-attr]
            except RedisError:
                logger.exception("failed to publish run job to redis; job stays queued job_id=%s", job_id)
        elif self.backend == "kafka":
            try:
                future = self.kafka_producer.send(self.kafka_topic, job_id)  # type: ignore[union-attr]
                future.get(timeout=10)
            except KafkaError:
                logger.exception("failed to publish run job to kafka; job stays queued job_id=%s", job_id)

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
        if self.queue.backend == "kafka":
            if self.queue.kafka_consumer is None:
                try:
                    self.queue.kafka_consumer = self.queue._create_kafka_consumer()
                except KafkaError:
                    logger.exception("failed to create kafka consumer; falling back to database polling once")
                    return self.queue.run_next_queued_job()
            if self.queue.kafka_consumer is None:
                return self.queue.run_next_queued_job()
            try:
                records = self.queue.kafka_consumer.poll(timeout_ms=self.queue.kafka_poll_timeout_ms, max_records=1)
            except KafkaError:
                logger.exception("kafka dequeue failed; falling back to database polling once")
                return self.queue.run_next_queued_job()
            for messages in records.values():
                for message in messages:
                    ran = self.queue.run_job_by_id(message.value)
                    self.queue.kafka_consumer.commit()
                    return ran
            return self.queue.run_next_queued_job()
        return self.queue.run_next_queued_job()
