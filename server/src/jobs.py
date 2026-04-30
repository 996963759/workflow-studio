import logging
from concurrent.futures import ThreadPoolExecutor

from .runner import simulate_run
from .storage import WorkflowStore


logger = logging.getLogger("workflow_studio.jobs")
executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="workflow-run")


class RunJobQueue:
    def __init__(self, store: WorkflowStore) -> None:
        self.store = store

    def enqueue(self, user_id: str, workspace_id: str, workflow_id: str, input_text: str):
        job = self.store.create_run_job(user_id, workspace_id, workflow_id, input_text)
        executor.submit(self._run_job, job.id, user_id, workspace_id, workflow_id, input_text)
        return job

    def _run_job(
        self,
        job_id: str,
        user_id: str,
        workspace_id: str,
        workflow_id: str,
        input_text: str,
    ) -> None:
        self.store.update_run_job(job_id, "running")
        try:
            workflow = self.store.get_workflow(workflow_id, user_id, workspace_id)
            if not workflow:
                raise RuntimeError("Workflow not found")
            response = simulate_run(workflow, input_text, user_id, workspace_id)
            run = self.store.create_run(
                workflow.id,
                user_id,
                workflow.name,
                input_text,
                response,
                workspace_id,
            )
            self.store.update_run_job(job_id, "succeeded", run_id=run.id)
        except Exception as error:  # noqa: BLE001 - stored as job error for the UI.
            logger.exception("run job failed job_id=%s", job_id)
            self.store.update_run_job(job_id, "failed", error=str(error))
