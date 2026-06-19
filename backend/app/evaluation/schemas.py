from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator


class GoldenQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str = Field(validation_alias=AliasChoices("id", "question_id"))
    question: str
    expected_article_ids: list[int] = Field(default_factory=list)
    expected_cluster_ids: list[int] = Field(default_factory=list)
    expected_title: str | None = None
    expected_outcome: str | None = None
    query_type: str | None = None
    question_type: str | None = None
    difficulty: str | None = None
    expected_answer_keywords: list[str] = Field(default_factory=list)
    expected_filters: dict = Field(default_factory=dict)
    requires_retrieval: bool = True
    is_multi_turn: bool = False
    scenario_id: str | None = None
    turn_index: int | None = None
    notes: str | None = None
    filters: dict = Field(default_factory=dict)
    top_k: int | None = None

    @field_validator("expected_article_ids", "expected_cluster_ids", "expected_answer_keywords", mode="before")
    @classmethod
    def _none_to_empty_list(cls, value):
        if value is None:
            return []
        return value

    @field_validator("top_k")
    @classmethod
    def _top_k_positive(cls, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError("top_k must be greater than zero.")
        return value

    @model_validator(mode="after")
    def _validate_evaluation_contract(self):
        if self.requires_retrieval and not self.expected_article_ids:
            raise ValueError("expected_article_ids must contain at least one article id.")
        if self.is_multi_turn and (not self.scenario_id or self.turn_index is None):
            raise ValueError("multi-turn questions require scenario_id and turn_index.")
        if self.turn_index is not None and self.turn_index < 1:
            raise ValueError("turn_index must be greater than zero.")
        return self


class RetrievalEvalResult(BaseModel):
    question_id: str
    question: str
    expected_article_ids: list[int]
    retrieved_article_ids: list[int]
    rewritten_query: str
    route_reason: str = ""
    filters: dict = Field(default_factory=dict)
    sort_by: str = "relevance"
    hit_at_k: bool
    recall_at_k: float
    precision_at_k: float
    mrr: float
    ndcg_at_k: float
    latency_ms: float
    top_k: int
    retrieval_mode: str = "hybrid"
    fusion_method: str = "rrf"
    bm25_index_status: str | None = None
    duplicate_rate: float = 0.0
    vector_result_count: int = 0
    bm25_result_count: int = 0
    hybrid_result_count: int = 0
    uses_rag: bool
    source_count: int
    citation_marker_count: int = 0
    has_sources_section: bool = False
    retrieved_context_empty: bool


class RetrievalEvalSummary(BaseModel):
    question_count: int
    hit_rate_at_k: float
    mean_recall_at_k: float
    mean_precision_at_k: float
    mean_mrr: float
    mean_ndcg_at_k: float
    mean_latency_ms: float
    bm25_index_status: str | None = None


class ClusteringEvalResult(BaseModel):
    article_count: int
    embedded_article_count: int
    clustered_article_count: int
    outlier_count: int
    cluster_count: int
    outlier_ratio: float
    cluster_assignment_coverage: float
    bertopic_outlier_count: int | None = None
    largest_cluster_ratio: float | None = None
    median_cluster_size: float | None = None
    silhouette_score: float | None = None
    davies_bouldin_score: float | None = None
    calinski_harabasz_score: float | None = None
    avg_intra_cluster_cosine_similarity: float | None = None
    avg_centroid_similarity: float | None = None
    skipped_reason: str | None = None
    pairwise_sample_limit: int
