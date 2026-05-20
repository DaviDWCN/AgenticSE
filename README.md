# AgenticSE — 自主多智能体软件工程团队

> **从"增强打字机"到"自动化流水线"**：一个端到端的自主 AI 工程团队框架，具备事件驱动工作流和自我进化能力。

---

## 架构概览 / Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        AgentTeam (团队入口)                      │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                    WorkflowEngine (工作流引擎)               │  │
│  │   任务图 (Task DAG) — 依赖解析 — 并发调度 — 重试机制         │  │
│  └──────────────────────────┬─────────────────────────────────┘  │
│                             │ 事件总线 (EventBus)                  │
│         ┌───────────────────┼──────────────────────┐             │
│         ▼                   ▼                      ▼             │
│  ┌─────────────┐   ┌─────────────────┐   ┌──────────────────┐   │
│  │ Orchestrator│   │  Specialist     │   │  LearnerAgent    │   │
│  │ (项目经理)   │   │  Agents (专家)  │   │  (自学习引擎)     │   │
│  │ 需求分析    │   │ • Planner 规划   │   │ 自动订阅回顾事件  │   │
│  │ 任务图生成  │   │ • Architect 架构 │   │ 分析 → 改进       │   │
│  │ 流程调度    │   │ • Developer 开发 │   │ 更新长期记忆       │   │
│  └─────────────┘   │ • Reviewer 审查  │   └──────────────────┘   │
│                    │ • QA 测试        │                           │
│                    └─────────────────┘                           │
│                                                                  │
│  ┌──────────────────┐   ┌──────────────────────────────────────┐ │
│  │  MemoryStore     │   │  SandboxExecutor (确定性沙盒)         │ │
│  │ • Short-term 短期│   │ • 隔离子进程执行 / CPU & 内存限制      │ │
│  │ • Long-term  长期│   │ • 超时保护 / 环境变量隔离             │ │
│  │ • Episodic   情节│   └──────────────────────────────────────┘ │
│  └──────────────────┘                                            │
└─────────────────────────────────────────────────────────────────┘
```

### 四大维度 / Four Pillars

| 维度 | 实现 | 说明 |
|------|------|------|
| **多智能体分工** | 7个专业 Agent | Orchestrator → Planner → Architect → Developer → Reviewer → QA → Learner |
| **事件驱动工作流** | `EventBus` + `WorkflowEngine` | 发布/订阅解耦，任务 DAG 依赖解析，并发调度 |
| **确定性沙盒** | `SandboxExecutor` | 隔离子进程，资源限制，超时保护，环境变量隔离 |
| **自我学习引擎** | `LearnerAgent` + `ProcessOptimizer` | 自动回顾 → 分析 → 改进流程指南 → 持久化记忆 |

---

## 目录结构 / Project Structure

```
agentse/
├── core/
│   ├── agent.py          # Agent 基类：生命周期管理、指标收集、事件发布
│   ├── event_bus.py      # 异步发布/订阅事件总线
│   ├── task.py           # Task 模型：DAG 依赖、状态机、重试
│   ├── memory.py         # 三层记忆存储（短期/长期/情节）
│   └── workflow.py       # 工作流引擎：依赖解析、并发调度
├── agents/
│   ├── orchestrator.py   # 项目经理：需求 → 任务图
│   ├── planner.py        # 规划员：里程碑、风险、工作量估算
│   ├── architect.py      # 架构师：组件设计、技术选型
│   ├── developer.py      # 开发者：代码框架生成
│   ├── reviewer.py       # 审查员：代码质量、安全检查
│   ├── qa.py             # 测试员：测试计划、覆盖率
│   └── learner.py        # 学习者：自动回顾、流程优化
├── sandbox/
│   └── executor.py       # 确定性沙盒代码执行器
├── learning/
│   ├── retrospective.py  # 迭代回顾分析
│   └── optimizer.py      # 流程优化引擎
├── team.py               # AgentTeam 工厂类（一键组装全团队）
└── cli.py                # 命令行界面
examples/
└── run_team.py           # 完整端到端示例
tests/                    # 55 个测试（单元 + 集成）
```

---

## 快速开始 / Quick Start

```bash
pip install -e .
python examples/run_team.py
```

### 代码示例

```python
import asyncio
from agentse.team import AgentTeam

async def main():
    team = AgentTeam()

    summary = await team.run_feature(
        title="User Authentication",
        description="Build a secure JWT authentication system with OAuth2 and bcrypt.",
    )

    print(f"Completed: {summary['completed']}/{summary['total']} tasks")
    print(f"Learning trend: {team.trend_report()}")

asyncio.run(main())
```

### CLI

```bash
agentse run --title "Payment Gateway" --description "Stripe integration with webhooks"
agentse status
agentse trends
```

---

## 自我学习循环 / Self-Learning Loop

```
Sprint N 运行
    → WorkflowEngine 发布 RETROSPECTIVE_TRIGGERED 事件
    → LearnerAgent 自动接收（事件订阅）
        ├─ 分析失败率 → 添加额外审查步骤
        ├─ 分析任务时长 → 调整优先级
        ├─ 分析覆盖率 → 更新覆盖率目标
        └─ 分析代码审查问题 → 更新反模式库
    → MemoryStore.set_long("process_guidelines", {...}) ← 持久化
    → Sprint N+1 OrchestratorAgent 读取改进后的指南
    → 更优的任务图、更高标准、更快交付
```

| 触发条件 | 学习动作 |
|---------|---------|
| 任务失败率 > 30% | 自动添加额外审查步骤 |
| 平均任务时长 > 5s | 提升关键 agent 调度优先级 |
| 测试覆盖率持续低于目标 | 动态调低覆盖率目标，再逐步拉高 |
| 测试覆盖率持续超过目标5% | 提高覆盖率目标 |
| 代码审查阻塞问题 > 2 | 扩充已知反模式库 |
| 某角色有≥3次重复行动项 | 提升该角色任务调度优先级 |

---

## 测试 / Testing

```bash
python -m pytest tests/ -v   # 55 tests, ~1.5s
```

---

## 设计原则 / Design Principles

1. **事件驱动解耦**：Agent 之间只通过事件通信，可独立替换和扩展
2. **记忆驱动进化**：所有经验持久化到 MemoryStore，指导下一次迭代
3. **确定性执行**：沙盒隔离保证代码执行安全可控
4. **重试与韧性**：任务失败自动重试，依赖失败自动取消下游
5. **可观测性**：结构化日志 + 事件历史 + Agent 指标，全程可追踪
