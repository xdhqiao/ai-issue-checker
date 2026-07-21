# 项目架构、实现流程与真实 LLM 验证记录

## 1. 项目架构

```text
Polyspace Client
       │ POST /api/tasks
       ▼
FastAPI Route ── Pydantic Schema ── TaskSubmissionService
                                           │
                                           ▼
                                MongoDB Task / CodeFile / Issue
                                           ▲
                                           │ lease + file checkpoint
APScheduler ── ReviewScheduler ── ReviewTaskService
                                      │ ThreadPoolExecutor
                                      ▼
                          IssueConfirmationService
                                      │
                       OpenAI-compatible function calling
                                      │
           ┌──────────────────────────┼─────────────────────────┐
           ▼                          ▼                         ▼
 read/search source tools     submit_confidences           task_done

MongoDB ── Admin/Report/Source APIs ── 管理页 / 任务报告页 / 源码弹窗
```

代码分层：

- `app/routes`：HTTP 入参、响应与页面入口，不承载复杂业务。
- `app/schemas`：Polyspace payload、任务列表、报告和源码响应的 Pydantic 校验。
- `app/models`：MongoEngine 的 Task、CodeFile，以及嵌入式 Issue、模型轮次和工具调用记录。
- `app/services/task_submission.py`：相同项目版本的旧数据清理和新任务落库。
- `app/services/scheduler.py`：任务轮询、原子租约领取、心跳与中断恢复。
- `app/services/review_service.py`：文件并发、文件检查点、任务聚合、重试和通知。
- `app/services/issue_confirmation.py`：真实 LLM 多轮 function calling 与置信度收集。
- `app/services/review_tools.py`：安全源码读取、搜索、符号检索以及完成工具。
- `app/static`：任务管理页与报告页。

## 2. 核心数据模型

### Task

一条 Task 对应一次 `project_id + review_version` 的 Polyspace 扫描结果。唯一索引保证同一项目版本只保留最新任务。Task 保存状态、文件/问题汇总、Token、LLM 调用次数、耗时、重试次数、worker lease 和邮件状态。

### CodeFile

CodeFile 归属于 Task，保存文件名、负责人、验证状态、文件级 LLM 指标、模型轮次、工具调用和 issue 数组。文件是最小恢复检查点；状态已经完成的文件不会重复调用模型。

### Issue

原样保存 `id/check/function/line/col/detail/severity_color/comment`。模型验证结束后只更新 `confidence`，不改写任何 Polyspace 原始字段。

## 3. 实现流程

1. Client 调用 `POST /api/tasks` 提交 Polyspace 扫描结果。
2. `TaskSubmissionService` 查找相同 `project_id + review_version`；存在时先删除旧 CodeFile，再删除旧 Task，然后写入本次完整数据。
3. `ReviewScheduler` 扫描 pending、允许重试的 failed、以及 lease 过期的 running 任务，通过带旧状态和旧 lease 的 MongoDB 原子更新领取任务。
4. `ReviewTaskService` 查询所有未完成文件，按 `FILE_CONCURRENCY` 使用线程池并发验证。
5. 每个文件传给模型的 issue 输入严格只有 `check/function/line/detail`。ID、列号、颜色、comment、负责人和文件名不进入提示词。
6. 模型通过 `read_file/code_search/file_find/find_definition/find_references/call_graph` 取证，通过 `submit_confidences` 按输入顺序提交 `0~1` 置信度，最后调用 `task_done`。
7. 只有文件内每条 issue 都有合法置信度时，才原子写入文件完成检查点。旧 worker 的 lease 已失效时不能覆盖新 worker 结果。
8. 全部文件完成后聚合任务指标、置为 completed，并按参考项目相同的管理员及文件负责人策略发送完成邮件。
9. 管理页和报告页直接读取聚合 API；源码 API 对根目录、路径穿越、符号链接和文件大小做限制。

## 4. 真实 LLM 测试

测试日期：2026-07-21  
模型：`deepseek-v4-flash`  
Task ID：`6a5f6d0039844d8ac9d96474`  
模拟输入：[polyspace_scan_v1.json](../demo_data/polyspace_scan_v1.json)

模拟代码包含两组对照：未经检查的除法/数组访问，以及已经完整检查的除法/数组访问。

| 文件 | Issue | Function | 代码事实 | LLM 置信度 |
|---|---:|---|---|---:|
| `Apps/Math/Math.c` | 8893 | `divide_unchecked()` | 除数没有零值检查 | 1.0 |
| `Apps/Math/Math.c` | 8894 | `divide_guarded()` | 除法前已经排除零值 | 0.0 |
| `Apps/Control/Control.c` | 9101 | `read_table()` | index 没有范围检查 | 1.0 |
| `Apps/Control/Control.c` | 9102 | `read_table_checked()` | 访问前已检查 `[0, 3]` | 0.0 |

运行指标：

- 状态：completed，进度 100%，2/2 文件完成。
- LLM API 调用：12 次，每个文件 6 轮。
- Prompt tokens：23,664。
- Completion tokens：3,012。
- Total tokens：26,676。
- LLM 累计耗时：34,651 ms。
- 任务墙钟处理时间：20,782 ms；两个文件并发处理，因此小于 LLM 累计耗时。
- 两个 CodeFile 的持久化 model trace 均记录模型 `deepseek-v4-flash`。

## 5. 结果链接

- [任务管理页](http://127.0.0.1:18080/admin/tasks.html)
- [本次真实 LLM 报告](http://127.0.0.1:18080/reports/6a5f6d0039844d8ac9d96474.html)
- [本次报告 JSON API](http://127.0.0.1:18080/api/reports/tasks/6a5f6d0039844d8ac9d96474)

当前 Docker 服务保留运行，以便直接访问上述链接。
