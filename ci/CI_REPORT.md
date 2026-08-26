# Transformers NPU CI 运行报告

> 数据来源:run [32940678535](https://github.com/UsernameFull/transformers-ci/actions/runs/32940678535)(commit `c248901ce5`,2026-08-26)。
> 本报告记录测试执行覆盖策略、未执行项的去向、以及当前失败家族的归因。上游每日同步,具体失败清单会漂移,但归因框架与豁免理由长期有效。

## 1. 执行总览

| job | 收集 | 通过 | 失败 | 跳过 |
|---|---|---|---|---|
| common | — | — | 93 | 471 |
| trainer | — | — | 42 | 153 |
| models | — | — | 22 | 121 |
| extra | — | — | 1 | 62 |
| **合计** | **5711** | **≈4746** | **158** | **807** |

- 所有 `test_path` 内的测试文件 100% 被 pytest 收集(junit 中无缺失文件、无 collection error、无 deselected——`-k` 排除清单已于 2026-08-15 全部移除,策略为"全量放开,红即信号")。

## 2. 未执行项的完整去向

每一类不执行的测试都有明确且文档化的理由:

### 2.1 `@slow` 用例(605 个)

工作日 `RUN_SLOW=0`,每周日 03:00 定时 run 自动置 `RUN_SLOW=1`(超时放宽到 600 分钟)。这是调度机制而非问题。周日会额外首次实跑 11 个 FA2 等价性测试(见 2.3)。

### 2.2 Flash Attention 家族

| 类别 | 数量 | 处理 |
|---|---|---|
| `requires Flash Attention`(FA2 门控) | 原 14 → **0** | 由 pytest 插件 `npu_fa2_unlock.py`(workflow 内联生成,`-p npu_fa2_unlock`)放行。原理:transformers 有原生 NPU FA2 实现(`integrations/npu_flash_attention.py`,走 `npu_fusion_attention`),不需要 CUDA-only 的 flash-attn 包;插件只替换 `testing_utils.require_flash_attn` 装饰器,**刻意不改** `is_flash_attn_2_available()` 等可用性函数——因为 `flash_attn_supports_top_left_mask()` 依赖其为 False 来启用 NPU 特有的 top-left causal mask 语义 |
| `requires Flash Attention 3 / 4` | 16 | **不可解锁**:FA3/FA4 是 Hopper/CUDA 专属内核,transformers 无任何 NPU 实现路径,kernels-community 也无 npu 变体 |
| `require_all_flash_attn` | 少量 | 需三者同时可用,随 FA3/FA4 保持跳过 |

### 2.3 硬件门控(~25 个)

`requires CUDA`、`CUDA graph`、`multiple CUDA GPUs`、`Peak memory tracking requires CUDA or XPU`、`requires MPS` 等——NPU 环境必然跳过,属上游设计。

其中 `test_memory_footprint_respects_max_memory_percent` 是上游显式写的 `skipTest("Peak memory tracking requires CUDA or XPU")`,说明上游已意识到该路径依赖 CUDA 显存语义。

### 2.4 单卡假设测试(10 个,`requires 0 or 1 accelerator`)

测试设计给"只看到 ≤1 张加速卡"的环境;runner 固定暴露 2 张 NPU 且 xdist 双 worker 共享,无法按 worker 注入 `ASCEND_RT_VISIBLE_DEVICES`,暂不处理。

### 2.5 mixin/common 参数化基类(14 个文件,登记于 `ci/test_exclusions.txt`)

`test_fsdp_mixin.py`、`test_tensor_parallel_mixin.py`、`test_modeling_common.py`、`test_pipeline_mixin.py` 等。这些文件自身无独立用例,实际通过**类继承**随各模型测试执行(qwen3 的 `test_tp_*` 即来自 tensor_parallel_mixin)。Coverage Watch 对其豁免。

### 2.6 其他模型目录(~890 文件,`tests/models/<其余模型>`)

既定策略:`models` job 只跑 `tests/models/qwen3` 作为全模型冒烟代表(qwen3 含 generation/trainer/distributed 类用例,覆盖面最广)。跑全部 400+ 模型需上游官方级别的分片集群。Coverage Watch 按顶层目录 `tests/models` 豁免,新模型目录仅信息展示。可考虑未来每周日增加代表性模型抽样。

### 2.7 整目录排除(登记于 `ci/test_exclusions.txt`)

| 目录 | 理由 |
| --- | --- |
| `tests/sagemaker` | 需要 AWS 账号与付费资源,aarch64 runner 无法收集 |
| `tests/kernels` | kernels-community 仅发布 cuda/xpu/rocm 预编译变体,npu 必挂(`test_kernels_can_load_without_crashing` 已单独排除) |
| `tests/quantization` | bitsandbytes 等量化后端不支持 NPU |
| `tests/fixtures`、`tests/conftest_tests` | 测试基建自检,非功能用例 |

### 2.8 上游主动禁用的零散 skip(~30 个)

`Broken for now TODO`、`This test is failing on main`、`model deleted`、序列化问题等——上游自己标注的禁用,与环境无关,无需处理。

### 2.9 可选依赖缺失(少量,低价值)

decord ×2(aarch64 无维护轮子)、detectron2 ×2(arm64 编译困难)、ONNXScript/ExecuTorch 各 1。收益低于成本,保持跳过。

## 3. 当前失败家族归因(158 个)

| 家族 | 数量 | 归因 | 解除条件 |
| --- | --- | --- | --- |
| **ACL-500001** `AclSetCompileopt ... internal ACL of the system is incorrect` | **43**(trainer 29 / common 12 / models 2) | **宿主机驱动/CANN 异常**,非代码问题。证据:①失败点均为各进程第一个 NPU 算子调用(adam 优化器、`tensor.to("npu")`、普通比较运算等互不相关的操作);②双卡同时中招;③两次独立 run 失败集合逐条一致(确定性复现);④8月24日同环境曾全绿 | 上机排查:`npu-smi info` → `fuser -v /dev/davinci*` 清理残留进程 → 设备复位/重启宿主机;核对宿主 driver/firmware 与容器 CANN 9.0.0 版本配对 |
| ContinuousBatching 缓存池超配 OOM + 显存预测断言 | ~17 | 上游硬编码:默认 `max_memory_percent=0.8/0.9` 按"空闲显存的 80~90%"分配 KV 缓存池,无环境变量开关;`TestMemoryHandlerPrediction` 断言依赖 CUDA 风格 memory stats(NPU 恒返回 delta=0) | 等上游适配 NPU 显存语义 |
| synthid watermark 巨型张量 OOM | ~5 | 测试构造 488~4882 GiB 单笔分配,物理不可行 | 不可修复,除非上游改测试 |
| torch.compile / triton-ascend 不兼容 | ~20 | `make_fallback(aten.gelu)` decomposition 冲突、`tl.sum(dtype=)` API 差异、flex_attention 无有效 config、`Adam.step(grad_scaler)` 要求 torch≥2.11 | 等 triton-ascend/torch 升级 |
| deepspeed resize embeddings IndexError(size 0) | 4 | meta-device 下 padding_idx 归零逻辑踩空 | 等上游 |
| NPU 数值精度差异 + expectation 表缺 npu 条目 | ~40 | pipeline 分数差在小数第 4 位、`No matching expectation found for ('npu', None, None)` 等 | 逐个为 npu 补 expectation 或放宽容差(上游 PR 级工作) |
| flaky / 上游抖动 | 若干 | 如 `test_length_warning_assisted_generation` 隔日翻转 | 观察 |

## 4. CI 内建的特殊机制备忘

| 机制 | 位置 | 说明 |
| --- | --- | --- |
| 上游 patch:get_device_properties | workflow `Patch upstream NPU bug` 步骤 | `testing_utils.py` 的 IS_NPU_SYSTEM 分支缺 `import torch`,精确字符串替换并断言唯一性 |
| FA2 解锁插件 | workflow `Enable native-NPU FlashAttention-2 tests` 步骤 | 内联生成 `npu_fa2_unlock.py`,`PYTHONPATH` 注入,仅 NPU 生效,失败不阻塞 pytest |
| torchcodec 源码构建 | Install dependencies(common 分支) | torch 2.10 只配 torchcodec 0.10,而 0.10 无 linux-aarch64 轮子且无 sdist;0.13+cpu 需 torch≥2.11;PyPI 默认轮子是 CUDA 构建缺 libnvrtc。故仅 common job 从 GitHub tag `v0.10.0` 源码编译(装 FFmpeg dev 头 + cmake/ninja),失败自动卸载回退 |
| HF_TOKEN | job env `HF_TOKEN: ${{ secrets.HF_TOKEN }}` | 解锁 gated repo(gemma-3-1b-it 等)。账号需先在模型页接受许可协议 |
| Coverage Watch | `coverage` job + `ci/check_coverage.py` | 看护顶层测试目录必须被 test_path 或 `ci/test_exclusions.txt` 覆盖,上游新增目录时强制人工确认(如 2026-08 新增的 `tests/pipeline_parallel` 已纳入 extra job) |

## 5. 失败分析方法论(供后续维护者)

1. `gh run download <run-id> -n test-reports-<job>` 取 junit XML;
2. 用脚本对比两次 run 的失败集合(fixed/added)、按错误签名聚类(AclSetCompileopt / OOM / ImportError / 断言);
3. 与上游源码交叉定位(镜像分支 `transformers-main` 可直接读源码);
4. 归因三问:是否首算子/初始化即失败(→环境)?是否跨无关功能同签名(→环境)?改动前后 A/B 是否一致(→定责)?
