# Batch Experiment Results

- Generation mode: real LLM
- Judge samples: 15
- A: plain_sot
- B: optimized KG method

## Category Averages

| Category | Method | Cases | Grounding | Hallucination risk | Graph structure | Dependencies | Evidence triples | Coherence | Judge avg |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fact_verification | optimized_json_kg | 5 | 0.340 | 0.660 | 0.360 | 2.40 | 8.60 | 0.400 | 8.480 |
| fact_verification | plain_sot | 5 | 0.000 | 1.000 | 0.000 | 0.00 | 0.00 | 0.000 | 8.520 |
| general_knowledge | optimized_json_kg | 5 | 0.000 | 1.000 | 0.000 | 0.40 | 0.00 | 0.200 | 8.680 |
| general_knowledge | plain_sot | 5 | 0.000 | 1.000 | 0.000 | 0.00 | 0.00 | 0.000 | 8.640 |
| logical_dependency | optimized_json_kg | 5 | 0.662 | 0.338 | 0.800 | 5.00 | 14.40 | 0.800 | 8.520 |
| logical_dependency | plain_sot | 5 | 0.000 | 1.000 | 0.000 | 0.00 | 0.00 | 0.060 | 8.040 |

## Judge Win Counts

| Winner | Count |
| --- | ---: |
| A | 4 |
| B | 10 |
| tie | 1 |

## Per Case Metrics

| ID | Category | Method | Grounding | Risk | Graph | Deps | Evidence | Judge avg | Fact | Rel | Struct | Clarity | Useful | Winner |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| general_001 | general_knowledge | plain_sot | 0.0 | 1.0 | 0.0 | 0 | 0 | 8.4 | 9 | 9 | 8 | 8 | 8 | B |
| general_001 | general_knowledge | optimized_json_kg | 0.0 | 1.0 | 0.0 | 1 | 0 | 9.0 | 9 | 9 | 9 | 9 | 9 | B |
| general_002 | general_knowledge | plain_sot | 0.0 | 1.0 | 0.0 | 0 | 0 | 8.8 | 9 | 9 | 8 | 9 | 9 | tie |
| general_002 | general_knowledge | optimized_json_kg | 0.0 | 1.0 | 0.0 | 0 | 0 | 8.8 | 9 | 9 | 8 | 9 | 9 | tie |
| general_003 | general_knowledge | plain_sot | 0.0 | 1.0 | 0.0 | 0 | 0 | 9.0 | 9 | 10 | 8 | 9 | 9 | B |
| general_003 | general_knowledge | optimized_json_kg | 0.0 | 1.0 | 0.0 | 0 | 0 | 9.2 | 9 | 10 | 9 | 9 | 9 | B |
| general_004 | general_knowledge | plain_sot | 0.0 | 1.0 | 0.0 | 0 | 0 | 8.6 | 9 | 9 | 8 | 9 | 8 | A |
| general_004 | general_knowledge | optimized_json_kg | 0.0 | 1.0 | 0.0 | 1 | 0 | 7.6 | 8 | 8 | 7 | 8 | 7 | A |
| general_005 | general_knowledge | plain_sot | 0.0 | 1.0 | 0.0 | 0 | 0 | 8.4 | 9 | 9 | 8 | 8 | 8 | B |
| general_005 | general_knowledge | optimized_json_kg | 0.0 | 1.0 | 0.0 | 0 | 0 | 8.8 | 9 | 9 | 8 | 9 | 9 | B |
| dependency_001 | logical_dependency | plain_sot | 0.0 | 1.0 | 0.0 | 0 | 0 | 8.2 | 9 | 9 | 8 | 7 | 8 | B |
| dependency_001 | logical_dependency | optimized_json_kg | 0.865 | 0.135 | 1.0 | 6 | 15 | 8.4 | 8 | 8 | 9 | 9 | 8 | B |
| dependency_002 | logical_dependency | plain_sot | 0.0 | 1.0 | 0.0 | 0 | 0 | 7.8 | 8 | 9 | 7 | 8 | 7 | B |
| dependency_002 | logical_dependency | optimized_json_kg | 0.79 | 0.21 | 1.0 | 7 | 26 | 8.6 | 9 | 9 | 8 | 9 | 8 | B |
| dependency_003 | logical_dependency | plain_sot | 0.0 | 1.0 | 0.0 | 0 | 0 | 7.8 | 8 | 9 | 7 | 7 | 8 | B |
| dependency_003 | logical_dependency | optimized_json_kg | 0.0 | 1.0 | 0.0 | 0 | 0 | 9.2 | 9 | 10 | 9 | 9 | 9 | B |
| dependency_004 | logical_dependency | plain_sot | 0.0 | 1.0 | 0.0 | 0 | 0 | 8.0 | 8 | 9 | 7 | 8 | 8 | B |
| dependency_004 | logical_dependency | optimized_json_kg | 0.867 | 0.133 | 1.0 | 6 | 14 | 9.2 | 9 | 10 | 9 | 9 | 9 | B |
| dependency_005 | logical_dependency | plain_sot | 0.0 | 1.0 | 0.0 | 0 | 0 | 8.4 | 8 | 9 | 8 | 9 | 8 | A |
| dependency_005 | logical_dependency | optimized_json_kg | 0.79 | 0.21 | 1.0 | 6 | 17 | 7.2 | 7 | 8 | 7 | 7 | 7 | A |
| verification_001 | fact_verification | plain_sot | 0.0 | 1.0 | 0.0 | 0 | 0 | 7.8 | 8 | 9 | 7 | 8 | 7 | B |
| verification_001 | fact_verification | optimized_json_kg | 0.88 | 0.12 | 0.8 | 7 | 26 | 9.2 | 9 | 10 | 9 | 9 | 9 | B |
| verification_002 | fact_verification | plain_sot | 0.0 | 1.0 | 0.0 | 0 | 0 | 8.8 | 9 | 9 | 8 | 9 | 9 | A |
| verification_002 | fact_verification | optimized_json_kg | 0.0 | 1.0 | 0.0 | 0 | 0 | 7.8 | 8 | 8 | 7 | 8 | 8 | A |
| verification_003 | fact_verification | plain_sot | 0.0 | 1.0 | 0.0 | 0 | 0 | 8.6 | 8 | 9 | 9 | 9 | 8 | A |
| verification_003 | fact_verification | optimized_json_kg | 0.0 | 1.0 | 0.0 | 0 | 0 | 7.6 | 7 | 8 | 8 | 8 | 7 | A |
| verification_004 | fact_verification | plain_sot | 0.0 | 1.0 | 0.0 | 0 | 0 | 8.8 | 9 | 9 | 8 | 9 | 9 | B |
| verification_004 | fact_verification | optimized_json_kg | 0.0 | 1.0 | 0.0 | 0 | 0 | 9.0 | 9 | 9 | 9 | 9 | 9 | B |
| verification_005 | fact_verification | plain_sot | 0.0 | 1.0 | 0.0 | 0 | 0 | 8.6 | 9 | 9 | 8 | 9 | 8 | B |
| verification_005 | fact_verification | optimized_json_kg | 0.82 | 0.18 | 1.0 | 5 | 17 | 8.8 | 9 | 9 | 9 | 8 | 9 | B |

## Per Question Pair View

| ID | Category | Query | Plain internal | KG internal | Plain external | KG external | Winner | Judge reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dependency_001 | logical_dependency | Why must an AI system verify retrieved evidence before aggregating an answer, and what can go wrong if these steps are executed in parallel without dependencies? | ground=0.0; risk=1.0; graph=0.0; deps=0; evidence=0; coherence=0.15 | ground=0.865; risk=0.135; graph=1.0; deps=6; evidence=15; coherence=1.0 | avg=8.2; fact=9; rel=9; struct=8; clarity=7; useful=8 | avg=8.4; fact=8; rel=8; struct=9; clarity=9; useful=8 | B | Answer B is more structured and clear, making it easier to understand. Both answers are factually accurate and relevant, but B's clarity and structure give it an edge. |
| dependency_002 | logical_dependency | Explain why entity linking should happen before knowledge graph retrieval in a grounded text generation pipeline. | ground=0.0; risk=1.0; graph=0.0; deps=0; evidence=0; coherence=0.0 | ground=0.79; risk=0.21; graph=1.0; deps=7; evidence=26; coherence=1.0 | avg=7.8; fact=8; rel=9; struct=7; clarity=8; useful=7 | avg=8.6; fact=9; rel=9; struct=8; clarity=9; useful=8 | B | Answer B provides a more structured and clear explanation, and it adds additional context about the benefits of entity linking which enhances its usefulness. |
| dependency_003 | logical_dependency | Why should a reasoning system build dependencies between claims before expanding them in parallel? | ground=0.0; risk=1.0; graph=0.0; deps=0; evidence=0; coherence=0.0 | ground=0.0; risk=1.0; graph=0.0; deps=0; evidence=0; coherence=0.0 | avg=7.8; fact=8; rel=9; struct=7; clarity=7; useful=8 | avg=9.2; fact=9; rel=10; struct=9; clarity=9; useful=9 | B | Answer B provides a more structured and clear explanation, enhancing the overall readability and coherence. It also offers a slightly higher level of detail and relevance to the question. |
| dependency_004 | logical_dependency | In a multi-step answer generation pipeline, why should contradiction checking happen before final summarization? | ground=0.0; risk=1.0; graph=0.0; deps=0; evidence=0; coherence=0.15 | ground=0.867; risk=0.133; graph=1.0; deps=6; evidence=14; coherence=1.0 | avg=8.0; fact=8; rel=9; struct=7; clarity=8; useful=8 | avg=9.2; fact=9; rel=10; struct=9; clarity=9; useful=9 | B | Answer B provides a more detailed and structured explanation, including the role of a dependency graph, which adds to its clarity and usefulness. It also maintains high factuality and relevance. |
| dependency_005 | logical_dependency | Explain why some thought nodes can be generated in parallel while others must wait for prerequisite evidence. | ground=0.0; risk=1.0; graph=0.0; deps=0; evidence=0; coherence=0.0 | ground=0.79; risk=0.21; graph=1.0; deps=6; evidence=17; coherence=1.0 | avg=8.4; fact=8; rel=9; struct=8; clarity=9; useful=8 | avg=7.2; fact=7; rel=8; struct=7; clarity=7; useful=7 | A | Answer A provides a more structured and clear explanation of the concept, directly addressing the question with relevant examples. It also maintains a good balance between factuality and usefulness. |
| general_001 | general_knowledge | Explain how AlphaFold changed protein structure prediction and what limitations remain. | ground=0.0; risk=1.0; graph=0.0; deps=0; evidence=0; coherence=0.0 | ground=0.0; risk=1.0; graph=0.0; deps=1; evidence=0; coherence=0.5 | avg=8.4; fact=9; rel=9; struct=8; clarity=8; useful=8 | avg=9.0; fact=9; rel=9; struct=9; clarity=9; useful=9 | B | Answer B provides a more structured and clear explanation, making it slightly easier to understand and more useful. |
| general_002 | general_knowledge | What are the main differences between supervised learning, unsupervised learning, and reinforcement learning? | ground=0.0; risk=1.0; graph=0.0; deps=0; evidence=0; coherence=0.0 | ground=0.0; risk=1.0; graph=0.0; deps=0; evidence=0; coherence=0.0 | avg=8.8; fact=9; rel=9; struct=8; clarity=9; useful=9 | avg=8.8; fact=9; rel=9; struct=8; clarity=9; useful=9 | tie | Both answers are factually correct, relevant, well-structured, clear, and useful. They provide a comprehensive comparison of the three types of machine learning paradigms. |
| general_003 | general_knowledge | Why are transformers important for modern natural language processing? | ground=0.0; risk=1.0; graph=0.0; deps=0; evidence=0; coherence=0.0 | ground=0.0; risk=1.0; graph=0.0; deps=0; evidence=0; coherence=0.0 | avg=9.0; fact=9; rel=10; struct=8; clarity=9; useful=9 | avg=9.2; fact=9; rel=10; struct=9; clarity=9; useful=9 | B | Answer B provides a more detailed comparison with previous models, which adds context and enhances the understanding of why transformers are important. |
| general_004 | general_knowledge | How do diffusion models generate images, and what are their main limitations? | ground=0.0; risk=1.0; graph=0.0; deps=0; evidence=0; coherence=0.0 | ground=0.0; risk=1.0; graph=0.0; deps=1; evidence=0; coherence=0.5 | avg=8.6; fact=9; rel=9; struct=8; clarity=9; useful=8 | avg=7.6; fact=8; rel=8; struct=7; clarity=8; useful=7 | A | Answer A provides a more detailed and clear explanation of the diffusion model process and its limitations, making it slightly more informative and useful for the user. |
| general_005 | general_knowledge | What is the role of embeddings in information retrieval systems? | ground=0.0; risk=1.0; graph=0.0; deps=0; evidence=0; coherence=0.0 | ground=0.0; risk=1.0; graph=0.0; deps=0; evidence=0; coherence=0.0 | avg=8.4; fact=9; rel=9; struct=8; clarity=8; useful=8 | avg=8.8; fact=9; rel=9; struct=8; clarity=9; useful=9 | B | Answer B is slightly more clear and useful, as it provides a bit more detail on the benefits of using embeddings over traditional keyword-based methods. |
| verification_001 | fact_verification | How can knowledge graphs help reduce hallucination in retrieval-augmented generation systems? | ground=0.0; risk=1.0; graph=0.0; deps=0; evidence=0; coherence=0.0 | ground=0.88; risk=0.12; graph=0.8; deps=7; evidence=26; coherence=1.0 | avg=7.8; fact=8; rel=9; struct=7; clarity=8; useful=7 | avg=9.2; fact=9; rel=10; struct=9; clarity=9; useful=9 | B | Answer B provides more detailed and specific ways in which knowledge graphs reduce hallucination, enhancing its factuality, relevance, and usefulness. It also has a clearer and more structured presentation. |
| verification_002 | fact_verification | Why can outdated evidence cause factual errors in AI-generated answers, and how should a system handle it? | ground=0.0; risk=1.0; graph=0.0; deps=0; evidence=0; coherence=0.0 | ground=0.0; risk=1.0; graph=0.0; deps=0; evidence=0; coherence=0.0 | avg=8.8; fact=9; rel=9; struct=8; clarity=9; useful=9 | avg=7.8; fact=8; rel=8; struct=7; clarity=8; useful=8 | A | Answer A provides a more detailed and structured approach to handling outdated evidence, including specific steps and the importance of transparency. It also offers a clearer explanation of why outdated evidence can cause errors. |
| verification_003 | fact_verification | How should an AI system handle two retrieved sources that make conflicting claims? | ground=0.0; risk=1.0; graph=0.0; deps=0; evidence=0; coherence=0.0 | ground=0.0; risk=1.0; graph=0.0; deps=0; evidence=0; coherence=0.0 | avg=8.6; fact=8; rel=9; struct=9; clarity=9; useful=8 | avg=7.6; fact=7; rel=8; struct=8; clarity=8; useful=7 | A | Answer A provides a more structured and clear explanation with specific steps, enhancing its usefulness and clarity. It also emphasizes the importance of transparency in decision-making, which is a key aspect for building user trust. |
| verification_004 | fact_verification | Why is source provenance important when generating answers from retrieved knowledge? | ground=0.0; risk=1.0; graph=0.0; deps=0; evidence=0; coherence=0.0 | ground=0.0; risk=1.0; graph=0.0; deps=0; evidence=0; coherence=0.0 | avg=8.8; fact=9; rel=9; struct=8; clarity=9; useful=9 | avg=9.0; fact=9; rel=9; struct=9; clarity=9; useful=9 | B | Answer B provides a slightly more detailed and structured explanation, particularly in emphasizing the importance of preventing the spread of misinformation and maintaining the professionalism and authority of the knowledge service. |
| verification_005 | fact_verification | Explain how evidence grounding improves the reliability of long-form generated reports. | ground=0.0; risk=1.0; graph=0.0; deps=0; evidence=0; coherence=0.0 | ground=0.82; risk=0.18; graph=1.0; deps=5; evidence=17; coherence=1.0 | avg=8.6; fact=9; rel=9; struct=8; clarity=9; useful=8 | avg=8.8; fact=9; rel=9; struct=9; clarity=8; useful=9 | B | Answer B provides a more detailed and structured explanation of the process of evidence grounding, including the steps involved and the benefits at each stage. It also addresses potential conflicts in sources, which adds depth to the answer. |