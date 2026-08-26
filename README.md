# Transformers 每日同步与长期 CI

自动镜像 `huggingface/transformers` 的 `main` 分支，并对每次上游更新执行轻量 CI。该仓库自身长期保持活动，避免 scheduled workflow 因 60 天无 repository activity 被 GitHub 自动停用。

> 📊 测试执行覆盖策略、skip/未执行项去向、失败家族归因详见 [`ci/CI_REPORT.md`](ci/CI_REPORT.md)。

## 分支结构

```text
main                仓库自身的 workflow、README 和 keepalive 文件
transformers-main   完整镜像 huggingface/transformers:main（完整历史，force push 更新）
```

## 工作流

| 工作流 | 触发 | 行为 |
| --- | --- | --- |
| `sync-and-ci.yml` | 每天 03:00 Asia/Shanghai；`workflow_dispatch` | 同步上游 `main` 到 `transformers-main`（无变化时不推送）；每次运行均并行执行 4 组 CI（common / trainer / models / extra）。**每周日 03:00 为长测试日**（`RUN_SLOW=1` 解锁 @slow 用例，超时放宽到 600 分钟） |
| `keepalive.yml` | 每天 03:37 Asia/Tokyo；`workflow_dispatch` | 距上次 Keepalive 提交满 15 天后更新 `.github/keepalive` 并提交，否则跳过 |

CI 并行 job（均使用 `linux-aarch64-a2-2` runner + CANN 容器镜像）：

| job | 覆盖范围 |
| --- | --- |
| `common` | `tests/utils tests/generation tests/pipelines tests/tokenization tests/cli tests/repo_utils` |
| `trainer` | `tests/trainer tests/optimization` |
| `models` | `tests/models/qwen3`（单目录；qwen3 的 generation/trainer 类测试在 2 核 CPU 上极慢，多目录会超时） |
| `extra` | `tests/exporters tests/integrations tests/kernels tests/heterogeneity tests/tensor_parallel tests/peft_integration tests/sagemaker`（onnx, onnxruntime, kernels, optuna, codecarbon, peft, sagemaker） |

缓存策略：runner 的 `/root/.cache` 目录为持久缓存目录（runner 主机保留），pip 下载缓存（`/root/.cache/pip`）与 HF 模型缓存（`HF_HOME=/root/.cache/huggingface`）跨 run 自动保留，无需 actions/cache 上传下载。

CI 完成后 `report` job（GitHub 托管 runner）用 `dorny/test-reporter` 汇总各 job 的 pytest junit 报告，发布为 commit 上的 **Transformers Test Results** check（汇总 + 失败用例明细，`use-actions-summary: false` 不使用 job summary）。

`coverage` job（Coverage Watch）看护测试覆盖：对照 `ci/covered_tests.txt` 清单扫描上游 `tests/`，上游新增顶层测试目录/文件未纳入清单时该 job 失败（强制人工确认），清单中路径消失也失败；`tests/models` 新增模型目录仅信息展示（模型按需选择）。

两个工作流使用独立的 concurrency group，互不取消。

## 安全边界

- 整个仓库工作流默认 `contents: read`，仅 sync 与 keepalive job 单独获得写权限。
- CI job 安装并执行上游代码，但没有仓库写权限，也不注入仓库密钥。
- sync 推送使用 SSH deploy key（secret `TRANSFORMERS_SYNC_SSH_KEY`，密钥文件位于 `$RUNNER_TEMP`，用后即删，不持久化）。
- keepalive 推送使用临时 `GIT_ASKPASS` 脚本（位于 `$RUNNER_TEMP`，用后即删）配合 `GITHUB_TOKEN`。

## 仓库变量（可选，批量生成时使用）

| 变量 | 默认值 |
| --- | --- |
| `UPSTREAM_URL` | `https://github.com/huggingface/transformers.git` |
| `UPSTREAM_BRANCH` | `main` |
| `MIRROR_BRANCH` | `transformers-main` |
| `HF_ENDPOINT` | `https://huggingface.co`（如网络受限可设为 `https://hf-mirror.com`，但镜像对 HEAD 元数据检查不兼容会导致部分测试失败） |

安装依赖为 `torch==2.12.0` + `torch_npu==2.12.0`（NPU 适配，torch_npu 2.12 硬性要求 torch 2.12）+ `.[torch,testing,vision]` + `librosa` + `torchcodec` + 可选依赖集（timm/av/pyctcdecode/peft/optuna/quanto/galore/apollo 等，bitsandbytes/torchao/liger/ray/lomo 软失败不阻断）。detectron2/executorch/flash-attn/MPS 类无法在 aarch64 CPU 安装，保持跳过。

> 已知环境特有失败：`test_qkv_chunk_rope_permute_with_fp8_quantization` 在 ARM64 CPU runner 上（triton 3.x 可用但 CPU 后端行为异常）会失败——上游测试假定 triton 在 GPU 上运行，属环境差异，非工作流问题。

## 仓库 Secret

| Secret | 用途 |
| --- | --- |
| `TRANSFORMERS_SYNC_SSH_KEY` | 推送镜像分支用的 SSH 私钥（对应仓库 writable deploy key） |

## 手动触发

- `Transformers Sync and CI`：`force_ci=true` 时即使上游无变化也运行 CI；可覆盖测试路径与 Python 版本。
- `Repository Keepalive`：立即检查是否需要 Keepalive 提交。

## 分支规则建议

- `main`：如启用 Ruleset，需为 `github-actions[bot]` 配置推送 `bypass`，或不对自动化仓库强制 PR。
- `transformers-main`：Ruleset `transformers-main mirror protection` 已生效（禁止创建/更新/删除/强推，bypass 仅授予仓库 writable deploy key）。

> 注：个人（用户）仓库无法把 GitHub Actions 集成添加为 ruleset bypass actor（API 报 "must be part of the ruleset source or owner organization"），因此镜像推送采用 SSH deploy key 认证；迁移到组织仓库后可改用 GitHub Actions 集成 bypass。

## 首次验收

1. 手动运行 `Repository Keepalive`：应创建 `.github/keepalive` 并产生 `chore: keep repository active` 提交；再次立即运行应跳过。
2. 手动运行 `Transformers Sync and CI`：比对 `huggingface/transformers` 的 `main` 与本仓库 `transformers-main` 的 SHA 应一致；上游无变化时 CI 被跳过，`force_ci=true` 时强制运行。
