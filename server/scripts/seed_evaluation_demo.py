"""Seed a 50-case evaluation demo dataset and run it once.

Usage:
    server\.venv\Scripts\python.exe server\scripts\seed_evaluation_demo.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("RUN_JOB_QUEUE_BACKEND", "thread")

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import select  # noqa: E402

from server.src import main as api  # noqa: E402
from server.src.models import EvaluationCaseResult, EvaluationDatasetPayload, WorkflowPayload  # noqa: E402
from server.src.orm import DbUser, DbWorkspaceMember, DbWorkspaceModelConfig  # noqa: E402
from server.src.runner import simulate_run  # noqa: E402


USERNAME = "eval_demo_user"
PASSWORD = "password123"
WORKFLOW_NAME = "评测演示工作流 - 大模型客服回复"
DATASET_NAME = "演示评测集：大模型客服场景关键词回归 50 条"


COMMON_KEYWORDS = [
    "退款",
    "售后",
    "人工客服",
    "物流",
    "换货",
    "退货",
    "发票",
    "开票",
    "会员",
    "积分",
    "优惠券",
    "地址",
    "支付",
    "质保",
    "维修",
    "包装",
    "活动",
    "价格",
    "库存",
    "取消订单",
    "修改订单",
    "订单",
    "账单",
    "企业微信",
    "SSO",
    "单点登录",
    "海外",
]


CASES = [
    ("商品还没发货，想申请退款。", ["退款", "订单"]),
    ("退款卡住了，需要联系谁处理？", ["退款", "人工客服"]),
    ("订单取消后钱什么时候退回？", ["取消订单", "退款"]),
    ("商品还没出库，能不能取消订单并退款。", ["订单", "取消订单", "退款"]),
    ("优惠券买的商品退款后优惠券还给吗？", ["优惠券", "退款"]),
    ("收到衣服尺码不合适，想退货。", ["退货", "售后"]),
    ("退货需要保留原包装吗？", ["退货", "包装"]),
    ("退货运费谁承担？", ["退货", "物流"]),
    ("退货后多久能看到退款？", ["退货", "退款"]),
    ("已经拆封还能退货吗？", ["退货"]),
    ("买错型号了，能不能换货？", ["换货"]),
    ("换货需要重新下单吗？", ["换货"]),
    ("收到破损商品想换货。", ["换货", "售后"]),
    ("换货一般多久发出？", ["换货"]),
    ("换货期间能不能查物流？", ["换货", "物流"]),
    ("我的快递到哪了？", ["物流", "订单"]),
    ("物流三天没更新怎么办？", ["物流", "人工客服"]),
    ("快递显示签收但我没收到。", ["物流", "售后"]),
    ("发错地址了可以改吗？", ["地址", "修改订单"]),
    ("订单刚下，能修改收货地址吗？", ["地址", "修改订单"]),
    ("我想开发票。", ["发票", "开票"]),
    ("公司报销需要专票。", ["发票", "开票"]),
    ("发票抬头写错了能重开吗？", ["发票"]),
    ("开票信息在哪里填？", ["开票", "订单"]),
    ("电子发票多久能收到？", ["发票", "订单"]),
    ("会员积分没有到账。", ["会员", "积分"]),
    ("积分能不能抵扣订单金额？", ["积分", "订单"]),
    ("会员等级怎么升级？", ["会员"]),
    ("优惠券用不了。", ["优惠券"]),
    ("活动券过期了能补发吗？", ["优惠券", "活动"]),
    ("支付失败但银行卡扣款了。", ["支付"]),
    ("重复支付了一笔怎么办？", ["支付", "退款"]),
    ("支付后订单状态还是未付款。", ["支付", "订单"]),
    ("账单金额和订单金额不一致。", ["账单", "订单"]),
    ("能不能修改订单里的支付方式？", ["支付", "修改订单"]),
    ("商品质保多久？", ["质保"]),
    ("质保期内坏了怎么维修？", ["质保", "维修"]),
    ("维修需要寄回原包装吗？", ["维修", "包装"]),
    ("维修进度在哪里查？", ["维修", "订单"]),
    ("超过质保还能维修吗？", ["质保", "维修"]),
    ("活动商品还有库存吗？", ["活动", "库存"]),
    ("价格刚降了能不能补差价？", ["价格", "售后"]),
    ("库存不够可以预订吗？", ["库存"]),
    ("活动价和页面价格不一致。", ["活动", "价格"]),
    ("地址填错了，想修改地址。", ["地址", "修改订单"]),
    ("海外订单可以修改收货地址吗？", ["海外", "地址"]),
    ("海外购买商品关税怎么处理？", ["海外", "清关说明"]),
    ("能否通过企业微信查看直播订单？", ["企业微信", "直播间工单"]),
    ("想开通 API 看数据。", ["API权限", "数据报表"]),
    ("是否支持本地部署？", ["Kubernetes", "私有化部署"]),
]


def demo_workflow_payload() -> WorkflowPayload:
    keyword_text = " ".join(COMMON_KEYWORDS)
    return WorkflowPayload(
        name=WORKFLOW_NAME,
        version="0.2.0",
        nodes=[
            {
                "id": "input-1",
                "position": {"x": 0, "y": 0},
                "data": {"kind": "input", "label": "用户问题", "outputKey": "user_request"},
            },
            {
                "id": "llm-reply",
                "position": {"x": 280, "y": 0},
                "data": {
                    "kind": "llm",
                    "label": "大模型客服回复",
                    "model": "deepseek-v4-flash",
                    "temperature": 0.2,
                    "maxOutputTokens": 500,
                    "timeoutSeconds": 45,
                    "systemPrompt": (
                        "你是一名电商客服质检助手。你要根据用户问题生成简洁、礼貌、可执行的中文客服回复。"
                        "如果问题属于候选关键词中的业务场景，请在回复中自然包含对应关键词，"
                        "并在最后追加一行“命中关键词：关键词1、关键词2”。"
                    ),
                    "prompt": (
                        "用户问题：{{user_request}}\n\n"
                        f"候选业务关键词：{keyword_text}\n\n"
                        "回复要求：\n"
                        "1. 先给出客服回复，不要编造订单结果。\n"
                        "2. 对需要人工处理的问题，引导联系人工客服或等待专员核对。\n"
                        "3. 最后一行必须输出“命中关键词：...”，只列出和用户问题相关的关键词。"
                    ),
                    "outputKey": "answer",
                },
            },
            {
                "id": "output-1",
                "position": {"x": 560, "y": 0},
                "data": {
                    "kind": "output",
                    "label": "最终回复",
                    "prompt": "{{answer}}",
                    "outputKey": "final_answer",
                },
            },
        ],
        edges=[
            {"id": "e-input-llm", "source": "input-1", "target": "llm-reply"},
            {"id": "e-llm-output", "source": "llm-reply", "target": "output-1"},
        ],
    )


def dataset_payload() -> EvaluationDatasetPayload:
    return EvaluationDatasetPayload(
        name=DATASET_NAME,
        description=(
            "覆盖退款、售后、物流、发票、会员、优惠券、地址、支付、质保等客服场景；"
            "末尾保留少量当前规则未覆盖的边界样例，用于展示失败明细。"
        ),
        cases=[
            {
                "input_text": input_text,
                "expected_output": "标准回复应覆盖该客服问题的关键处理方向。",
                "expected_keywords": expected_keywords,
            }
            for input_text, expected_keywords in CASES
        ],
    )


def get_or_create_demo_user() -> str:
    user = api.auth_service.get_user_by_username(USERNAME)
    if user:
        return user.id
    return api.auth_service.create_user(USERNAME, PASSWORD).user.id


def select_seed_target() -> tuple[str, str, str, bool]:
    """Prefer a workspace that already has an enabled DeepSeek config."""
    preferred_username = os.getenv("EVAL_DEMO_USERNAME", "").strip().lower()
    with api.store._connect() as session:
        statement = (
            select(DbUser.id, DbUser.username, DbWorkspaceMember.workspace_id)
            .join(DbWorkspaceMember, DbWorkspaceMember.user_id == DbUser.id)
            .join(
                DbWorkspaceModelConfig,
                DbWorkspaceModelConfig.workspace_id == DbWorkspaceMember.workspace_id,
            )
            .where(
                DbWorkspaceModelConfig.provider == "deepseek",
                DbWorkspaceModelConfig.enabled.is_(True),
            )
            .order_by(DbWorkspaceModelConfig.updated_at.desc())
        )
        if preferred_username:
            statement = statement.where(DbUser.username == preferred_username)
        row = session.execute(statement).first()
    if row:
        user_id, username, workspace_id = row
        return str(user_id), str(workspace_id), str(username), True

    user_id = get_or_create_demo_user()
    workspace_id = api.store.ensure_default_workspace(user_id, USERNAME)
    return user_id, workspace_id, USERNAME, False


def upsert_workflow(user_id: str, workspace_id: str):
    payload = demo_workflow_payload()
    existing = next(
        (workflow for workflow in api.store.list_workflows(user_id, workspace_id) if workflow.name == WORKFLOW_NAME),
        None,
    )
    if existing:
        updated = api.store.update_workflow(existing.id, payload, user_id, workspace_id)
        if updated is None:
            raise RuntimeError("Failed to update demo workflow")
        return updated
    return api.store.create_workflow(payload, user_id, workspace_id)


def upsert_dataset(user_id: str, workspace_id: str):
    payload = dataset_payload()
    existing = next(
        (
            dataset
            for dataset in (api.store.list_evaluation_datasets(user_id, workspace_id) or [])
            if dataset.name == DATASET_NAME
        ),
        None,
    )
    if existing:
        updated = api.store.update_evaluation_dataset(existing.id, payload, user_id, workspace_id)
        if updated is None:
            raise RuntimeError("Failed to update demo evaluation dataset")
        return updated
    created = api.store.create_evaluation_dataset(payload, user_id, workspace_id)
    if created is None:
        raise RuntimeError("Failed to create demo evaluation dataset")
    return created


def run_evaluation(user_id: str, workspace_id: str, workflow, dataset):
    results: list[EvaluationCaseResult] = []
    llm_steps = 0
    real_model_steps = 0
    fallback_errors: list[str] = []
    model_configs = api.workspace_model_configs(workspace_id)
    for case in dataset.cases:
        response = simulate_run(workflow, case.input_text, user_id, workspace_id, model_configs)
        for step in response.steps:
            if step.kind == "llm":
                llm_steps += 1
                if step.provider and "DeepSeek" in step.provider and not step.error:
                    real_model_steps += 1
                if step.error:
                    fallback_errors.append(step.error)
        run = api.store.create_run(workflow.id, user_id, workflow.name, case.input_text, response, workspace_id, workflow)
        output = api.final_output_from_response(response)
        passed, missing_keywords = api.evaluate_case_output(output, case.expected_keywords)
        results.append(
            EvaluationCaseResult(
                case_id=case.id,
                input_text=case.input_text,
                expected_keywords=case.expected_keywords,
                output=output,
                passed=passed and response.status == "ok",
                missing_keywords=missing_keywords,
                status=response.status,
                duration_ms=sum(step.duration_ms for step in response.steps),
                run_id=run.id,
                error=next((step.error for step in response.steps if step.error), None),
            )
        )
    evaluation_run = api.store.create_evaluation_run(dataset, workflow, user_id, workspace_id, results)
    return evaluation_run, llm_steps, real_model_steps, fallback_errors


def main() -> None:
    user_id, workspace_id, username, has_model_config = select_seed_target()
    workflow = upsert_workflow(user_id, workspace_id)
    dataset = upsert_dataset(user_id, workspace_id)
    evaluation_run, llm_steps, real_model_steps, fallback_errors = run_evaluation(user_id, workspace_id, workflow, dataset)

    print("Seeded 50-case evaluation demo.")
    print(f"Username: {username}")
    if username == USERNAME:
        print(f"Password: {PASSWORD}")
    print(f"Workflow: {workflow.name}")
    print(f"Dataset: {dataset.name}")
    print(f"Workspace has DeepSeek config: {has_model_config}")
    print(f"LLM steps: {llm_steps}, real model steps: {real_model_steps}, fallback steps: {llm_steps - real_model_steps}")
    if fallback_errors:
        print(f"First fallback error: {fallback_errors[0]}")
    print(
        "Result: "
        f"{evaluation_run.passed_cases}/{evaluation_run.total_cases} passed, "
        f"{evaluation_run.failed_cases} failed, pass rate {evaluation_run.pass_rate}%"
    )


if __name__ == "__main__":
    main()
