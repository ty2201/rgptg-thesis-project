# Wikidata 小型知识图谱导入 Neo4j

本项目默认选择 Wikidata 的 `Artificial intelligence (Q11660)` 作为人工智能类别根实体，抓取一个小型主题子图。

## 1. 抓取数据

```powershell
$env:PYTHONPATH="src"
python -m rgptg.wikidata --topic Q11660 --limit 40 --output data/wikidata_ai_sample.json --cypher outputs/wikidata_ai_import.cypher
```

输出：

- `data/wikidata_ai_sample.json`：本地 JSON 图数据；
- `outputs/wikidata_ai_import.cypher`：Neo4j 可执行导入语句。

## 2. 导入 Neo4j

如果使用本项目帮你安装到 E 盘的 Neo4j 5.26.25，可以先用管理员权限启动：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_neo4j_e.ps1
powershell -ExecutionPolicy Bypass -File scripts/neo4j_console_e.ps1
```

其中 `neo4j_console_e.ps1` 会以前台 console 方式启动 Neo4j。当前本机路径为：

```text
E:\neo4j-codex\neo4j-5.26.25
E:\neo4j-codex\jdk-21
```

先确保 Neo4j 正在运行，并设置密码：

```powershell
$env:NEO4J_URI="bolt://localhost:7687"
$env:NEO4J_USER="neo4j"
$env:NEO4J_PASSWORD="你的密码"
```

然后执行：

```powershell
$env:PYTHONPATH="src"
python -m rgptg.wikidata --topic Q11660 --limit 40 --import-neo4j
```

如果已经抓取过本地 JSON，不想重复访问 Wikidata，可以直接从本地文件导入：

```powershell
$env:PYTHONPATH="src"
python -m rgptg.wikidata --from-json data/wikidata_ai_sample.json --import-neo4j
```

## 3. 在 Neo4j Browser 中检查

```cypher
MATCH (e:Entity) RETURN e LIMIT 25;
```

```cypher
MATCH (h:Entity)-[r]->(t:Entity)
RETURN h.name, type(r), t.name
LIMIT 50;
```

## 4. 与项目管线结合

如果要让主生成管线使用 Neo4j 数据源，可以在配置文件中设置：

```json
{
  "kg": {
    "provider": "neo4j",
    "neo4j_uri": "bolt://localhost:7687",
    "neo4j_user_env": "NEO4J_USER",
    "neo4j_password_env": "NEO4J_PASSWORD"
  }
}
```

当前 `Neo4jKnowledgeGraph` 会从 Neo4j 拉取一份小型内存快照，再交给规则引擎使用。
