"""MCP 外部能力接入层（infra，**不感知任何领域**）。

## 接入一个新的 MCP server：四步（client/registry 零改动）

1. **加配置**（管理员级 `.env`，两处模板同步，AGENTS §7）：
   ```jsonc
   MCP_SERVERS=[{"name":"my-server","command":"","args":["-m","some_module"],
                 "env":{"MY_KEY":"..."},"tool":"my_tool","adapter":"my_adapter_v1"}]
   ```
   - `command` 留空 = 用当前解释器（推荐，避开 Windows `python` 商店桩）；
   - `cwd` 缺省 = backend 根目录；`enabled:false` 可单独停用某个 server；
   - `timeout_seconds` 可单独覆盖该 server 的调用超时。
2. **写适配器**（领域侧，如 `app/funds/quotes.py`）：
   `register_adapter("my_adapter_v1", fn)`，`fn(payload, codes) -> list[领域对象]`；
   `payload` 形状 `{"server","structured","text","is_error"}`——结构化优先、文本兜底，
   第三方 server 的 `{"result": ...}` 包裹在适配层解包，**校验与丢弃脏数据也在这一层做**。
3. **包一层领域工具**（`app/tools/xxx_tool.py` + `@registry.register`）：
   LLM 只见领域工具，不见 MCP 原始 schema（设计 P0.5）；用 `app.core.prompts` 定界外部数据。
4. **补测试**：协议用 `tests/support/stub_*.py`（真 stdio、假数据，不联网）；
   适配器校验用纯单测（外部数据一律不可信，AGENTS §6.6）。

## 已有接缝（F1 起可用）

- 白名单：只允许 `MCP_SERVERS` 中声明的 server 与 tool 名（不猜）；
- 降级：`MCP_ENABLED=false` / 未配置 → 调用抛 `MCPError`，领域工具转可读提示，不炸主链路；
- 韧性：超时/异常**丢弃会话**，下次调用自动重连（被取消的 stdio 会话不可复用）；
- 脱敏：`mask_env()` + `app.core.redaction.redact()`——**env 值永不进日志**；
- 截断：第三方 server 的工具描述截断到 `DESCRIPTION_MAX`（防 prompt 被污染）。
"""
