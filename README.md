# Transformers 每日同步与长期 CI

自动镜像 `huggingface/transformers` 的 `main` 分支，并对每次上游更新执行轻量 CI。该仓库自身长期保持活动，避免 scheduled workflow 因 60 天无 repository activity 被 GitHub 自动停用。

## 分支结构

```text
main                仓库自身的 workflow、README 和 keepalive 文件
transformers-main   完整镜像 huggingface/transformers:main（完整历史，force push 更新）
```

## 工作流

| 工作流 | 触发 | 行为 |
| --- | --- | --- |
| `sync-and-ci.yml` | 每天 03:17 Asia/Tokyo；`workflow_dispatch` | 同步上游 `main` 到 `transformers-main`；镜像 SHA 变化时对新 commit 运行 CI，无变化时跳过 CI |
| `keepalive.yml` | 每天 03:37 Asia/Tokyo；`workflow_dispatch` | 距上次 Keepalive 提交满 15 天后更新 `.github/keepalive` 并提交，否则跳过 |

两个工作流使用独立的 concurrency group，互不取消。

## 安全边界

- 整个仓库工作流默认 `contents: read`，仅 sync 与 keepalive job 单独获得写权限。
- CI job 安装并执行上游代码，但没有仓库写权限，也不注入仓库密钥。
- 推送使用临时 `GIT_ASKPASS` 脚本（位于 `$RUNNER_TEMP`，用后即删），不持久化凭据。

## 仓库变量（可选，批量生成时使用）

| 变量 | 默认值 |
| --- | --- |
| `UPSTREAM_URL` | `https://github.com/huggingface/transformers.git` |
| `UPSTREAM_BRANCH` | `main` |
| `MIRROR_BRANCH` | `transformers-main` |
| `PYTHON_VERSION` | `3.12` |
| `CI_TEST_PATH` | `tests/utils` |

## 手动触发

- `Transformers Sync and CI`：`force_ci=true` 时即使上游无变化也运行 CI；可覆盖测试路径与 Python 版本。
- `Repository Keepalive`：立即检查是否需要 Keepalive 提交。

## 分支规则建议

- `main`：如启用 Ruleset，需为 `github-actions[bot]` 配置推送 `bypass`，或不对自动化仓库强制 PR。
- `transformers-main`：严格镜像上游，仅允许 GitHub Actions force push；禁止人工修改或提交自定义文件（下次同步会覆盖）。

## 首次验收

1. 手动运行 `Repository Keepalive`：应创建 `.github/keepalive` 并产生 `chore: keep repository active` 提交；再次立即运行应跳过。
2. 手动运行 `Transformers Sync and CI`：比对 `huggingface/transformers` 的 `main` 与本仓库 `transformers-main` 的 SHA 应一致；上游无变化时 CI 被跳过，`force_ci=true` 时强制运行。
