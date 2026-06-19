from datetime import date

from pydantic import BaseModel, Field, model_validator


class BulletinPreferenceRequest(BaseModel):
    selection_type: str
    cluster_ids: list[int] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    limit: int = Field(default=10, ge=1, le=50)
    include_digests: bool = True
    notifications_enabled: bool = True

    @model_validator(mode="after")
    def validate_selection(self):
        if self.selection_type not in {"clusters", "categories"}:
            raise ValueError("selection_type must be 'clusters' or 'categories'.")
        if self.selection_type == "clusters" and not self.cluster_ids:
            raise ValueError("At least one cluster must be selected.")
        if self.selection_type == "categories" and not self.categories:
            raise ValueError("At least one category must be selected.")
        return self


class WeeksBestBulletinRequest(BaseModel):
    selection_type: str
    selection_id: str
    week_start: date
    week_end: date
    force_refresh: bool = False
    use_llm: bool = False

    @model_validator(mode="after")
    def validate_weeks_best_request(self):
        if self.selection_type not in {"cluster", "category"}:
            raise ValueError("selection_type must be 'cluster' or 'category'.")
        if not self.selection_id.strip():
            raise ValueError("selection_id is required.")
        if self.week_end < self.week_start:
            raise ValueError("week_end must be on or after week_start.")
        return self
