# Dynamic KG-guided DAG

当前项目的 KG 引导算法不再固定生成 `n1,n2,n3,n4` 四个节点。

`KGGraphBuilder` 会先根据问题链接实体并检索 KG 三元组，然后按以下因素动态决定证据节点数量：

- 问题复杂度：例如“如何、为什么、比较、优化、风险、流程”等问题会倾向于保留更多分支。
- 关系多样性：检索到的关系类型越多，越倾向于生成更多不同角度的节点。
- 实体覆盖范围：涉及实体越丰富，越倾向于扩展为更细的 DAG。
- 三元组置信度与问题匹配度：更相关、更可信的三元组优先进入节点。

动态结构的一般形式是：

```text
n1: 问题语义锚定节点
n2..nk: KG 证据节点
n(k+1): 聚合终端证据节点
```

当 KG 里存在链式关系时，节点之间会形成真正的 DAG，而不是全部从 `n1` 平铺出去。例如：

```text
KG --supports--> Verification
Verification --reduces--> Hallucination
KG --reduces--> Hallucination
```

会生成类似结构：

```text
n1 -> n2: KG reduces Hallucination
n1 -> n3: KG supports Verification
n3 -> n4: Verification reduces Hallucination
n2 + n4 -> n5: aggregate
```

这样，知识图谱优化的是“回答之前的思维图结构”：证据少时自动退化为小图，关系丰富时自动扩展为多分支、多层依赖的 DAG。
