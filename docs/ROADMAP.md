# Roadmap

> 愿景记录（2026-08-10）。细节待后续细化，先占位跟踪。

## 愿景

从"agent 状态灯"演进为 **provider 状态指示工具栏工具**——一个菜单栏工具，同时提供：

- **signal-light**（已有）：agent 工作状态指示（灯语系统、Codex / Claude Code / omp / pi-coding-agent hooks 集成、多会话聚合）。
- **provider-usage**（规划）：provider 用量提示——token 用量、余额、配额等，让 AI 助手及其使用的模型服务的"状态"在菜单栏一屏可见。

## 待定项（后续细化）

- provider 用量数据来源：API 余额端点（如 Anthropic/OpenAI usage API）、本地网关/代理统计、hook 侧 token 计数汇总？
- 展示形态：现有菜单栏图标扩展（分区域/子菜单）、详情面板扩展，还是独立状态项？
- 支持的 provider 范围与用量口径（token、金额、配额、重置周期）。
- 与现有 `sessions.json` 聚合/灯语体系的关系（独立信号还是并入聚合优先级）。

## 备注

- 实现遵循现有架构约定：单一 Swift 二进制、JSON 文件契约、launchd 自启。
- nightly 构建 hook 已就绪，代码变更 push 自动打包上传。
