import logging
import time
from concurrent.futures import ThreadPoolExecutor

try:
    from kafka import KafkaConsumer, KafkaProducer
    from kafka.errors import KafkaError
except ImportError:  # pragma: no cover - thread-backed tests do not need Kafka.
    KafkaConsumer = None  # type: ignore[assignment]
    KafkaProducer = None  # type: ignore[assignment]

    class KafkaError(Exception):
        pass

from .config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_CONSUMER_GROUP,
    KAFKA_POLL_TIMEOUT_MS,
    KAFKA_RUN_JOB_TOPIC,
    RUN_JOB_POLL_INTERVAL_SECONDS,
    RUN_JOB_QUEUE_BACKEND,
    RUN_EXECUTION_MODE,
    RUN_JOB_WORKERS,
)
from .models import RunJobRecord, RunResponse, RunStep
from .runner import simulate_run
from .storage import WorkflowStore


logger = logging.getLogger("workflow_studio.jobs")
executor = ThreadPoolExecutor(max_workers=RUN_JOB_WORKERS, thread_name_prefix="workflow-run")


class RunJobQueue:
    def __init__(
        self,
        store: WorkflowStore,
        backend: str = RUN_JOB_QUEUE_BACKEND,
        kafka_bootstrap_servers: str = KAFKA_BOOTSTRAP_SERVERS,
        kafka_topic: str = KAFKA_RUN_JOB_TOPIC,
        kafka_consumer_group: str = KAFKA_CONSUMER_GROUP,
        kafka_poll_timeout_ms: int = KAFKA_POLL_TIMEOUT_MS,
        kafka_producer=None,
        execution_mode: str = RUN_EXECUTION_MODE,
    ) -> None:
        if backend not in {"kafka", "thread"}:
            raise ValueError("RUN_JOB_QUEUE_BACKEND must be kafka; thread is only for automated tests")
        self.store = store
        self.backend = backend
        self.kafka_bootstrap_servers = kafka_bootstrap_servers
        self.kafka_topic = kafka_topic
        self.kafka_consumer_group = kafka_consumer_group
        self.kafka_poll_timeout_ms = kafka_poll_timeout_ms
        self.execution_mode = execution_mode
        self.kafka_producer = kafka_producer or (
            self._create_kafka_producer(kafka_bootstrap_servers) if backend == "kafka" else None
        )
        self.kafka_consumer = None

    def _create_kafka_producer(self, bootstrap_servers: str):
        if KafkaProducer is None:
            raise RuntimeError("kafka-python package is required when RUN_JOB_QUEUE_BACKEND=kafka")
        try:
            return KafkaProducer(
                bootstrap_servers=[server.strip() for server in bootstrap_servers.split(",") if server.strip()],
                value_serializer=lambda value: value.encode("utf-8"),
                acks="all",
            )
        except KafkaError:
            logger.exception("failed to create kafka producer")
            raise

    def _create_kafka_consumer(self):
        if KafkaConsumer is None:
            raise RuntimeError("kafka-python package is required when RUN_JOB_QUEUE_BACKEND=kafka")
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
        job = self.store.create_run_job(
            user_id,
            workspace_id,
            workflow_id,
            input_text,
            self.execution_mode,
        )
        self.publish(job.id)
        return job

    def publish(self, job_id: str) -> None:
        if self.backend == "thread":
            executor.submit(self.run_job_by_id, job_id)
        elif self.backend == "kafka":
            try:
                future = self.kafka_producer.send(self.kafka_topic, job_id)  # type: ignore[union-attr]
                future.get(timeout=10)
            except KafkaError:
                logger.exception("failed to publish run job to kafka job_id=%s", job_id)
                raise

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
        active_run_id: str | None = None
        try:
            workflow = self.store.get_workflow_for_job(job.workflow_id, job.id)
            if not workflow:
                raise RuntimeError("Workflow not found")
            run = self.store.ensure_run_for_job(job.id, workflow)
            active_run_id = run.id
            user_id = self.store.get_run_job_user_id(job.id)
            workspace_id = self.store.get_run_job_workspace_id(job.id)
            model_configs = {}
            deepseek_config = self.store.get_runtime_model_config_for_job(job.id, "deepseek")
            if deepseek_config:
                model_configs["deepseek"] = deepseek_config
            aliyun_config = self.store.get_runtime_model_config_for_job(job.id, "aliyun")
            if aliyun_config:
                model_configs["aliyun"] = aliyun_config
            paismart_config = self.store.get_runtime_model_config_for_job(job.id, "paismart")
            if paismart_config:
                model_configs["paismart"] = paismart_config
            response = simulate_run(
                workflow,
                job.input_text,
                user_id,
                workspace_id,
                model_configs,
                execution_mode=job.execution_mode,
                progress_callback=lambda progress: self.store.update_run_progress(run.id, progress),
                cancel_check=lambda: self.store.is_run_job_cancel_requested(job.id),
                run_id=run.id,
                initial_steps=run.steps,
            )
            self.store.update_run_progress(run.id, response)
            if response.status == "canceled":
                self.store.update_run_job(job.id, "canceled", run_id=run.id, error="用户已取消任务。")
            elif response.status == "error":
                last_error = next((step.error for step in reversed(response.steps) if step.error), None)
                self.store.update_run_job(job.id, "failed", run_id=run.id, error=last_error or "工作流运行失败。")
            elif response.status == "degraded":
                self.store.update_run_job(
                    job.id,
                    "degraded",
                    run_id=run.id,
                    error="运行完成，但至少一个节点使用了模拟或降级输出。",
                )
            else:
                self.store.update_run_job(job.id, "succeeded", run_id=run.id)
        except Exception as error:  # noqa: BLE001 - stored as job error for the UI.
            logger.exception("run job failed job_id=%s", job.id)
            if active_run_id:
                current = self.store.get_run(
                    active_run_id,
                    self.store.get_run_job_user_id(job.id),
                    self.store.get_run_job_workspace_id(job.id),
                )
                existing_steps = current.steps if current else []
                failure = RunResponse(
                    status="error",
                    execution_mode=job.execution_mode,
                    steps=[
                        *existing_steps,
                        RunStep(
                            node_id="workflow-runtime-error",
                            title="运行时异常",
                            status="error",
                            input="异步 Worker",
                            output="工作流运行被异常中断。",
                            kind="workflow",
                            error=str(error),
                        ),
                    ],
                )
                self.store.update_run_progress(active_run_id, failure)
            self.store.update_run_job(job.id, "failed", run_id=active_run_id, error=str(error))


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
        if self.queue.backend == "kafka":
            if self.queue.kafka_consumer is None:
                self.queue.kafka_consumer = self.queue._create_kafka_consumer()
            try:
                records = self.queue.kafka_consumer.poll(timeout_ms=self.queue.kafka_poll_timeout_ms, max_records=1)
            except KafkaError:
                logger.exception("kafka dequeue failed")
                raise
            for messages in records.values():
                for message in messages:
                    ran = self.queue.run_job_by_id(message.value)
                    self.queue.kafka_consumer.commit()
                    return ran
            return False
        if self.queue.backend == "thread":
            return self.queue.run_next_queued_job()
        raise ValueError("RUN_JOB_QUEUE_BACKEND must be kafka; thread is only for automated tests")
