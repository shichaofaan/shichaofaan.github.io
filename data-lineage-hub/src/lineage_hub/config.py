from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ds_api_url: str = "http://localhost:12345/dolphinscheduler"
    ds_token: str = ""
    ds_project_codes: str = ""
    ds_ui_base_url: str = "http://localhost:12345/dolphinscheduler/ui"

    yuque_api_url: str = "https://www.yuque.com/api/v2"
    yuque_token: str = ""
    yuque_book_namespace: str = ""

    git_repo_paths: str = "./tests/fixtures/git_repo"
    git_blob_base_url: str = ""

    lineage_db_path: Path = Field(default=Path("./data/lineage.db"))

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    @property
    def project_codes(self) -> list[int]:
        if not self.ds_project_codes.strip():
            return []
        return [int(x.strip()) for x in self.ds_project_codes.split(",") if x.strip()]

    @property
    def git_paths(self) -> list[Path]:
        return [Path(p.strip()).expanduser() for p in self.git_repo_paths.split(",") if p.strip()]


def get_settings() -> Settings:
    return Settings()
