# ai-issue-checker

`ai-issue-checker` 接收 Polyspace 扫描结果，通过 LLM + function calling 读取对应版本源码，对每条 issue 做二次确认，并将 `0~1` 的置信度写回 issue 对象。项目沿用本地 `ci-ai-codereview` 的 FastAPI、MongoEngine、MongoDB、调度租约、文件并发、工具调用追踪、邮件边界与静态报告页架构，去掉 diff、plan_task、五维评分和快照等无关模型。

## 技术架构

```text
Polyspace client
      │ POST /api/tasks
      ▼
FastAPI routes → Pydantic schemas → TaskSubmissionService
                                      │
                                      ▼
                              MongoDB (Task/CodeFile/Issue)
                                      ▲
                                      │ lease + checkpoint
APScheduler → ReviewScheduler → ReviewTaskService → file thread pool
                                               │
                                               ▼
                              IssueConfirmationService
                                  │ function calling
                                  ▼
                              OpenAI-compatible LLM
                                  │
                                  ├─ read_file / code_search / file_find
                                  ├─ find_definition / find_references / call_graph
                                  ├─ submit_confidences
                                  └─ task_done

Admin / Author statistics / Report pages ← report/admin/source APIs ← MongoDB
Completion → same admin + file-owner email recipient strategy as ci-ai-codereview
```

## 数据模型

- `TaskModel`：一次 `project_id + review_version` 扫描任务，记录状态、汇总数量、LLM 用量、耗时、重试与租约。
- `CodeFileModel`：任务下的文件，记录负责人、验证状态、LLM 调用/Token/耗时、工具轮次与 issue 列表。
- `Issue`（嵌入 CodeFile）：原样保存 `id/check/function/line/col/detail/severity_color/comment`，验证完成后只增加或更新 `confidence`。

状态值统一为：`0 pending`、`1 running`、`2 completed`、`3 failed`。任务表对 `(project_id, review_version)` 建唯一索引。

## 实现流程

1. Client 调用 `POST /api/tasks`。若数据库中已有相同 `project_id + review_version`，先删除旧任务下全部 CodeFile，再删除旧 Task，随后完整写入新数据。
2. 后台调度器轮询 pending、可重试 failed，以及租约已过期的 running 任务。领取使用带旧状态和旧租约条件的原子 `modify`，避免多个实例重复领取。
3. 一个任务内按 `FILE_CONCURRENCY` 并发处理文件。已完成文件直接跳过；中断或失败文件重新处理。
4. 每个文件调用 LLM 多轮 function calling。传给 LLM 的 issue 输入对象严格只有 `check/function/line/detail` 四个字段。文件名、负责人、id、col、严重等级和 comment 不进入提示词。
5. 模型通过源码工具取证，调用 `submit_confidences` 按输入顺序提交置信度，再调用 `task_done`。只有全部 issue 都有合法 `0~1` 置信度才建立文件完成检查点。
6. 所有文件完成后聚合指标、完成任务并发邮件。若失败，在退避时间后重试未完成文件；部署中断时，任务租约过期后可恢复。

## 目录结构

```text
app/
  common/       状态和任务类型常量
  core/         环境配置、数据库、统一异常
  models/       MongoEngine Task/CodeFile/Issue
  schemas/      API 入参与响应模型
  routes/       task、admin、report、source、health API
  services/     提交、调度、文件验证、LLM、tools、邮件、报表
  static/       管理任务、人员统计/明细与报告页面
  templates/    完成邮件模板
tests/          API、重复清理、恢复、LLM 输入边界、报告测试
```

## 启动

### Docker Compose

```bash
cp .env.example .env  # 可选；Compose 未找到 .env 时也会使用安全默认值
mkdir -p repositories
docker compose up --build
```

将代码仓库父目录通过 `CODE_REPOSITORY_HOST_PATH` 挂载到容器 `/ShareData`，API 的 `version_code_path` 应使用容器内路径。例如 `/ShareData/integration/engine-ecu/v1`。

- API 文档：`http://127.0.0.1:8000/docs`
- 管理页面：`http://127.0.0.1:8000/admin/tasks.html`
- 人员统计：`http://127.0.0.1:8000/admin/authors.html`
- 健康检查：`http://127.0.0.1:8000/health`

### 本地 Python 3.12

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
copy .env.example .env
.venv/Scripts/uvicorn app.main:app --reload
```

Linux/macOS 下将 `.venv/Scripts/...` 换成 `.venv/bin/...`。

## 主要 API

### 提交扫描结果

```http
POST /api/tasks
Content-Type: application/json
```

```json
{
  "project_id": "engine-ecu",
  "review_version": "v1",
  "version_code_path": "/ShareData/integration/engine-ecu/v1",
  "files": [{
    "file_name": "Apps/Math/Math.c",
    "file_author": "dahai",
    "issues": [{
      "id": 8893,
      "check": "Division by zero",
      "function": "AdjMethCct_inner_default_DFC()",
      "line": 716,
      "col": 59,
      "detail": "Warning: scalar division by zero may occur",
      "severity_color": "red",
      "comment": "..."
    }]
  }]
}
```

其它接口：

- `GET /api/tasks`、`GET /api/tasks/{task_id}`、`DELETE /api/tasks/{task_id}`
- `GET /api/admin/tasks`：筛选、排序、分页
- `GET /api/admin/authors`：按日期统计负责人
- `GET /api/admin/authors/{author}`：按日期、问题等级查看负责人相关项目版本明细
- `GET /api/reports/tasks/{task_id}`：报告及负责人/文件分页
- `GET /api/reports/projects/{project_id}/versions/{review_version}`：按项目和版本读取报告
- `GET /api/code-files/{file_id}/source`：安全读取报告对应源码
- `GET /reports/{project_id}/{review_version}.html`：友好地址报告页面
- `GET /reports/{task_id}.html`：兼容原任务 ID 报告地址

## 关键配置

- `FILE_CONCURRENCY`：单任务文件并发度。
- `APP_HOST_PORT`：Docker 映射到宿主机的端口，默认 `8000`；端口冲突时可改为例如 `18080`。
- `SCHEDULER_*`：轮询、租约、最大重试、退避和关闭等待。
- `LLM_*`：OpenAI-compatible `/chat/completions` 地址、密钥、模型、重试、轮次和文件超时。
- `LLM_MOCK_ENABLED=true`：不访问模型，所有 issue 写入中性测试置信度 `0.5`；生产必须设为 `false` 并配置 `LLM_URL`。
- `CODE_REPOSITORY_ROOT`：允许读取的版本目录总根，生产建议必须配置。
- `EMAIL_*`：与 `ci-ai-codereview` 相同的管理员和负责人邮箱生成策略。当前 `EmailServer` 与参考项目一致，是可替换的日志/模板网关边界。

## 测试

测试使用 mongomock，不要求启动 MongoDB：

```bash
pytest
```

覆盖健康检查、任务写入与汇总、相同项目版本全量清理、路径穿越拒绝、中断租约恢复、文件检查点、LLM 四字段输入约束、管理筛选、人员维度聚合、友好报告地址、报告和源码读取。
