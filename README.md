# 规则引导的并行文本生成

这是一个根据开题报告搭建的研究型原型项目。项目目标是在 Skeleton of Thought (SoT) 的“先生成骨架、再并行扩展”框架上，引入知识图谱约束、Graph of Thoughts 依赖图、规则校验和结构化聚合，以缓解骨架质量不稳定、全局一致性不足和强逻辑任务处理能力弱的问题。

## 项目提纲

完整提纲见 [docs/project_outline.md](docs/project_outline.md)。

更细的算法设计见 [docs/algorithm_design.md](docs/algorithm_design.md)。

Wikidata 到 Neo4j 的数据准备说明见 [docs/wikidata_neo4j.md](docs/wikidata_neo4j.md)。

核心模块：

- 知识图谱层：加载实体、关系、三元组，支持实体链接、邻域检索和关系校验。
- 骨架规划层：从用户问题生成结构化节点，每个节点包含论点、实体、关系、依赖和置信度。
- 规则校验层：根据 KG 强约束、依赖关系和置信度对节点剪枝或降级。
- DAG 调度层：把可并行节点并发扩展，把有依赖节点串行等待。
- 聚合层：统一术语、消解冲突，并输出结构化长文本。
- 评测层：输出延迟、覆盖度、连贯性、依赖数量等轻量指标。
- CLI：提供命令行入口，便于实验和演示。

## 快速运行

如果当前环境没有安装本项目，可先在项目根目录运行：

```powershell
$env:PYTHONPATH="src"
python -m rgptg.cli "知识图谱如何降低并行文本生成的幻觉"
```

程序会输出：

1. 动态思维图节点；
2. 被规则剪枝或降级的节点；
3. 并行/串行调度结果；
4. 最终生成文本。

## 导出思维图

导出 Mermaid：

```powershell
$env:PYTHONPATH="src"
python -m rgptg.cli "比较 SoT 与 CoT 在复杂推理任务中的差异" --mermaid
```

导出 Graphviz DOT：

```powershell
$env:PYTHONPATH="src"
python -m rgptg.cli "比较 SoT 与 CoT 在复杂推理任务中的差异" --dot
```

## 批量实验

```powershell
$env:PYTHONPATH="src"
python -m rgptg.experiment --input examples/tasks.jsonl --output outputs/experiment_results.json
```

实验结果会包含每个任务在 `direct`、`sot`、`rule_guided` 三种方法下的规则事件、最终文本、Mermaid 图和轻量级指标。脚本还会额外生成 `outputs/experiment_results.summary.csv`，方便整理实验表格。

只运行指定方法：

```powershell
$env:PYTHONPATH="src"
python -m rgptg.experiment --methods direct,rule_guided
```

## 可选依赖

核心原型不需要额外安装库。如果要接真实模型或 Neo4j，可以安装：

```powershell
pip install -r requirements-optional.txt
```

配置文件可以从 [config.example.json](config.example.json) 复制后修改。默认仍使用本地 mock 模型和 `data/sample_kg.json`。

使用配置文件运行：

```powershell
$env:PYTHONPATH="src"
$env:OPENAI_API_KEY="你的模型服务密钥"
python -m rgptg.cli "知识图谱如何降低 SoT 并行生成中的幻觉" --config config.example.json
```

DashScope / Qwen OpenAI-compatible 示例配置见：

```text
config.dashscope.example.json
```

运行前设置环境变量：

```powershell
$env:DASHSCOPE_API_KEY="你的 DashScope API Key"
$env:NEO4J_USER="neo4j"
$env:NEO4J_PASSWORD="你的 Neo4j 密码"
$env:PYTHONPATH="src"
python -m rgptg.cli "知识图谱如何降低并行生成中的幻觉" --config config.dashscope.example.json
```

## Wikidata 数据导入 Neo4j

抓取人工智能主题的小型 Wikidata 子图：

```powershell
$env:PYTHONPATH="src"
python -m rgptg.wikidata --topic Q11660 --limit 40
```

如果 Neo4j 已启动并配置好密码，可以直接导入：

```powershell
$env:NEO4J_PASSWORD="你的密码"
python -m rgptg.wikidata --topic Q11660 --limit 40 --import-neo4j
```

已抓取本地 JSON 后，也可以不再访问 Wikidata，直接导入 Neo4j：

```powershell
$env:NEO4J_PASSWORD="你的密码"
python -m rgptg.wikidata --from-json data/wikidata_ai_sample.json --import-neo4j
```

本机已安装的短路径 Neo4j：

```text
E:\neo4j-codex\neo4j-5.26.25
E:\neo4j-codex\jdk-21
```

## 知识图谱优化验证

```powershell
$env:PYTHONPATH="src"
python -m rgptg.kg_ablation --output outputs/kg_ablation_results.json
```

验证报告见：

- `outputs/kg_optimization_report.md`
- `outputs/kg_ablation_results.md`
- `outputs/kg_ablation_results.csv`
- `outputs/kg_quality_report.md`

## KG-guided DAG 结构优化

项目现在默认启用 KG-guided DAG 构建，会优先用 KG 证据生成：

```text
n1 -> n2
n1 -> n3
n2 + n3 -> n4
```

可用参数关闭：

```powershell
python -m rgptg.cli "知识图谱如何降低幻觉？" --no-kg-graph-builder
```

## 真实 LLM 完整流程

为了避免真实模型调用过多导致超时，可以限制节点数并可选跳过最终聚合：

```powershell
$env:DASHSCOPE_API_KEY="你的 DashScope API Key"
$env:NEO4J_USER="neo4j"
$env:NEO4J_PASSWORD="你的 Neo4j 密码"
$env:PYTHONPATH="src"
python -m rgptg.real_llm_run "How can artificial intelligence systems use knowledge graphs to reduce hallucination?" --config config.dashscope.example.json --max-nodes 3 --skip-aggregate
```

输出：

- `outputs/real_llm_full_run.json`
- `outputs/real_llm_full_run.md`

扩展阶段默认限制较短输出：

```json
"expand_max_tokens": 360
```

## 后续可接入方向

- 将 `rgptg.llm.LLMClient` 替换为 Qwen、Llama、OpenAI API 或 vLLM 调用。
- 将 `data/sample_kg.json` 替换为 Neo4j / GraphRAG / 领域知识图谱。
- 在 HotpotQA、GSM8K 等数据集上补充指标评测。
- 增加缓存、异步检索、关键路径优先调度和可视化 DAG。
