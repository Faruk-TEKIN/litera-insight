# Professional Prompt for Writing the `APPLICATION RESULTS AND TESTS` Section in LaTeX

## Purpose

Use this prompt to ask an AI assistant or a technical writer to help prepare the `APPLICATION RESULTS AND TESTS` section of a graduation project report.

The final report section must be written in **Turkish**, but this prompt is written in **English** so that the assistant clearly understands the task, structure, constraints, and expected output quality.

The report should be suitable for a **software engineering graduation project**. The language must be clear, academic, and understandable. Avoid unnecessarily complex, advanced, or overly technical words unless they are required for the project.

---

# Master Prompt

```text
You are a senior software engineering report writer and AI/RAG evaluation specialist.

I am writing a graduation project report in LaTeX. The project is an academic publication intelligence and analysis platform. The system collects academic papers from external sources, cleans and stores them in a database, generates embeddings, clusters papers into topics, and provides a RAG-based academic question-answering assistant.

The report section I need to write is:

APPLICATION RESULTS AND TESTS

Important language requirement:
- The final report text must be written in Turkish.
- The Turkish language must be clear, simple, and understandable.
- Do not use unnecessarily complex, advanced, or artificial academic words.
- Use a formal but readable graduation project report style.
- Avoid exaggerated claims.
- Do not write as if the system is perfect.
- Mention limitations honestly.
- The text must be suitable for a university graduation project report.

Technical writing requirement:
- The output must be LaTeX compatible.
- Use proper LaTeX section and subsection commands.
- Do not use Markdown headings in the final report text.
- Use LaTeX tables where useful.
- Use placeholders such as X, Y, or TODO where real numbers must be inserted later.
- Do not invent experimental results.
- If exact values are unknown, write placeholder values and explain what should be inserted.
- The report must be structured enough to be directly copied into a LaTeX report.

Project context:
The project is an academic publication intelligence and analysis platform with the following main components:

1. Data Collection:
   - Collects academic publications from sources such as arXiv, OpenAlex, and Semantic Scholar.
   - Stores publication metadata such as title, abstract, authors, source, DOI, publication year, citation count, and PDF links.

2. Data Cleaning:
   - Removes duplicate or incomplete records.
   - Filters records with missing or very short titles and abstracts.
   - Produces a cleaner dataset for embedding, clustering, and retrieval.

3. Embedding Generation:
   - Uses a sentence embedding model such as multilingual E5.
   - Combines title, abstract, and metadata to create vector representations.
   - Stores embeddings in PostgreSQL with pgvector.

4. Topic Clustering:
   - Uses BERTopic with UMAP, HDBSCAN, and c-TF-IDF.
   - Groups articles into meaningful research topics.
   - Produces topic keywords, representative articles, and cluster metadata.
   - Since clustering is unsupervised, it is evaluated with internal metrics such as topic coherence, Silhouette score, and Davies-Bouldin index.

5. RAG-Based Question Answering:
   - Uses a router to decide whether a user question needs database retrieval.
   - Rewrites user questions for better retrieval.
   - Extracts filters such as year, category, source, citation count, DOI, and PDF availability.
   - Performs semantic search using pgvector.
   - Applies lightweight reranking.
   - Sends retrieved context to a local LLM.
   - Generates answers with source citations such as [S1], [S2], etc.

6. Backend and Frontend:
   - Backend is implemented with FastAPI.
   - Frontend is implemented with React, Vite, TypeScript, and Tailwind CSS.
   - PostgreSQL is used as the main database.
   - Docker and Docker Compose are used for local development.

7. Evaluation Mechanism:
   - A golden set of questions is prepared.
   - Each question has expected article IDs, question type, and expected answer properties.
   - The evaluation checks retrieval quality, citation correctness, answer grounding, and system behavior.
   - Metrics may include Hit@1, Hit@3, Hit@5, Recall@5, MRR, Citation Precision, and Citation Recall.
   - The evaluation should separate different error types such as router error, retrieval error, citation error, generation error, and memory error.

Your task:
Write a detailed and professional `APPLICATION RESULTS AND TESTS` section for this graduation project report in Turkish.

The section must include the following structure:

\section{Application Results and Tests}

\subsection{Değerlendirme Sürecine Genel Bakış}
Explain what this section evaluates. Mention that the system was tested from data processing, clustering, RAG, citation, integration, and performance perspectives.

\subsection{Deney Ortamı}
Explain the hardware and software environment. Include a LaTeX table with components such as backend, frontend, database, embedding model, clustering method, LLM runtime, and development environment.

\subsection{Veri Hazırlama Sonuçları}
Explain data collection and cleaning results. Include a table with placeholders:
- Raw collected articles
- Removed duplicate records
- Removed records with missing abstracts
- Removed records with short or low-quality text
- Final clean articles

Do not invent values. Use TODO or X placeholders.

\subsection{Embedding ve Vektör Depolama Sonuçları}
Explain how article embeddings were generated and stored in PostgreSQL with pgvector. Mention why this step is important for semantic search and RAG. Include a table with placeholders:
- Embedding model
- Embedding dimension
- Number of embedded articles
- Batch size
- Failed records
- Stored vectors

\subsection{Konu Kümeleme Sonuçları}
Explain BERTopic clustering results. Mention that there is no ground-truth label because the task is unsupervised. Therefore, internal metrics were used. Include a table with:
- Number of clustered articles
- Number of generated topics
- Number of outlier articles
- Topic coherence score
- Silhouette score
- Davies-Bouldin index

Also include a short explanation of what these metrics mean in simple Turkish.

\subsection{RAG Tabanlı Soru-Cevap Sonuçları}
Explain the RAG flow:
User question -> routing -> query rewriting -> metadata filtering -> vector retrieval -> reranking -> answer generation -> citation.

Include an example table with:
- User question
- Rewritten query
- Retrieved sources
- Generated answer summary
- Citation format

Use placeholders where real examples should be inserted.

\subsection{Golden Set ile Değerlendirme}
Explain how the golden set was used. Mention question categories such as:
- Exact paper lookup
- Semantic topic search
- Metadata/filter question
- Comparative question
- Follow-up memory question
- Out-of-domain question

Include a table showing the number of questions per category with placeholders.

Then include another table for retrieval metrics:
- Hit@1
- Hit@3
- Hit@5
- Recall@5
- MRR

Then include another table for citation and answer quality:
- Citation Precision
- Citation Recall
- Grounded Answer Ratio
- Unsupported Answer Ratio
- Manual Answer Score

Explain these metrics in simple Turkish.

\subsection{Sistem ve Entegrasyon Testleri}
Explain backend, frontend, database, AI pipeline, RAG router, retrieval service, and conversation memory tests. Include a table:
- Test type
- Purpose
- Expected result
- Status

Use placeholders such as Passed, Failed, or TODO.

\subsection{Performans Sonuçları}
Explain measured or planned performance values. Include a table with placeholders:
- Average RAG response time
- Vector retrieval time
- Embedding generation time
- Clustering execution time
- Dashboard loading time

Do not invent values.

\subsection{Hata Analizi}
Explain how errors were categorized. Include categories:
- Router error
- Query rewriting error
- Filter extraction error
- Retrieval miss
- Reranking error
- Citation error
- Generation error
- Conversation memory error
- System timeout or backend error

Explain that this separation helps identify which part of the system should be improved.

\subsection{Sınırlılıklar}
Write a realistic limitations section. Mention:
- The golden set is limited in size.
- Clustering does not have ground-truth labels.
- Local LLM performance may be lower than larger commercial models.
- Local development environment may not represent production-scale performance.
- Citation correctness may require manual checking.
- Dataset coverage depends on the selected academic sources.

\subsection{Genel Değerlendirme}
Summarize that the system successfully integrates data collection, cleaning, embedding generation, clustering, RAG-based question answering, and citation-based responses. Mention that the tests show the main components work together, but also reveal areas for future improvement.

Important style rules:
- Write in Turkish.
- Keep sentences clear and direct.
- Avoid overly long sentences.
- Do not use very complex academic words.
- Do not exaggerate results.
- Use passive academic style where appropriate.
- Use LaTeX syntax correctly.
- Tables must be valid LaTeX.
- Use placeholders instead of fake numbers.
- The section should be detailed enough for a graduation report.
- The writing should sound natural, not machine-generated.
- Do not mention that the text was generated by AI.
- Do not include this prompt in the output.
- Only output the final LaTeX section.
```

---

# Additional Guidance for the Writer

The writer should focus on proving that the project works through measurable evidence. The section should not only describe screens or features. It should explain how each part of the system was tested and what kind of result was obtained.

The most important idea is:

```text
The system should not only produce an answer; it should retrieve the right academic evidence, use it correctly, cite it properly, and produce a grounded response.
```

The report should make this idea clear in simple Turkish.

---

# Recommended Final LaTeX Structure

The final output should follow this structure:

```latex
\section{Application Results and Tests}

\subsection{Değerlendirme Sürecine Genel Bakış}

\subsection{Deney Ortamı}

\subsection{Veri Hazırlama Sonuçları}

\subsection{Embedding ve Vektör Depolama Sonuçları}

\subsection{Konu Kümeleme Sonuçları}

\subsection{RAG Tabanlı Soru-Cevap Sonuçları}

\subsection{Golden Set ile Değerlendirme}

\subsection{Sistem ve Entegrasyon Testleri}

\subsection{Performans Sonuçları}

\subsection{Hata Analizi}

\subsection{Sınırlılıklar}

\subsection{Genel Değerlendirme}
```

---

# Suggested Tables

## Experimental Environment Table

```latex
egin{table}[H]
\centering
\caption{Deney Ortamı}
egin{tabular}{ll}
\hline
Bileşen & Kullanılan Teknoloji \
\hline
Backend & FastAPI \
Frontend & React, Vite, TypeScript, Tailwind CSS \
Veritabanı & PostgreSQL + pgvector \
Embedding Modeli & intfloat/multilingual-e5-base \
Kümeleme Yöntemi & BERTopic, UMAP, HDBSCAN, c-TF-IDF \
LLM Çalıştırma Ortamı & Ollama \
Dil Modeli & TODO: Kullanılan model adı \
Geliştirme Ortamı & TODO: İşletim sistemi ve donanım bilgisi \
\hline
\end{tabular}
\end{table}
```

## Dataset Preparation Table

```latex
egin{table}[H]
\centering
\caption{Veri Hazırlama Sonuçları}
egin{tabular}{lr}
\hline
İşlem Adımı & Makale Sayısı \
\hline
Toplanan ham makale sayısı & TODO \
Silinen tekrar kayıt sayısı & TODO \
Eksik abstract nedeniyle silinen kayıt sayısı & TODO \
Kısa veya düşük kaliteli metin nedeniyle silinen kayıt sayısı & TODO \
Son temiz makale sayısı & TODO \
\hline
\end{tabular}
\end{table}
```

## Clustering Metrics Table

```latex
egin{table}[H]
\centering
\caption{Konu Kümeleme Değerlendirme Sonuçları}
egin{tabular}{lr}
\hline
Metrik & Değer \
\hline
Kümeleme için kullanılan makale sayısı & TODO \
Üretilen konu sayısı & TODO \
Outlier makale sayısı & TODO \
Topic coherence skoru & TODO \
Silhouette skoru & TODO \
Davies-Bouldin indeksi & TODO \
\hline
\end{tabular}
\end{table}
```

## Golden Set Retrieval Metrics Table

```latex
egin{table}[H]
\centering
\caption{Golden Set Retrieval Sonuçları}
egin{tabular}{lr}
\hline
Metrik & Skor \
\hline
Hit@1 & TODO \
Hit@3 & TODO \
Hit@5 & TODO \
Recall@5 & TODO \
MRR & TODO \
\hline
\end{tabular}
\end{table}
```

## Citation Quality Table

```latex
egin{table}[H]
\centering
\caption{Kaynak Gösterimi ve Cevap Kalitesi Sonuçları}
egin{tabular}{lr}
\hline
Metrik & Skor \
\hline
Citation Precision & TODO \
Citation Recall & TODO \
Grounded Answer Ratio & TODO \
Unsupported Answer Ratio & TODO \
Manuel Cevap Skoru & TODO \
\hline
\end{tabular}
\end{table}
```

---

# Checklist Before Using the Generated Section

Before inserting the generated section into the report, check the following:

```text
[ ] The text is written in Turkish.
[ ] The language is clear and not overly complex.
[ ] The section uses LaTeX syntax.
[ ] No fake results are invented.
[ ] All unknown values are marked as TODO.
[ ] Dataset results are shown in a table.
[ ] Embedding and pgvector results are explained.
[ ] Clustering results and metrics are included.
[ ] RAG answer generation is explained.
[ ] Golden set evaluation is included.
[ ] Retrieval metrics are included.
[ ] Citation metrics are included.
[ ] Integration tests are included.
[ ] Performance results are included.
[ ] Limitations are written honestly.
[ ] The final summary connects results to the project goals.
```
