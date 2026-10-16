"""Runtime settings, read once from the project-root .env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    glm_api_key: str = os.getenv("GLM_API_KEY", "")
    glm_base_url: str = os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
    glm_model: str = os.getenv("GLM_MODEL", "glm-5.3")
    glm_fast_model: str = os.getenv("GLM_FAST_MODEL", os.getenv("GLM_MODEL", "glm-5.3"))
    glm_deep_effort: str = os.getenv("GLM_DEEP_EFFORT", "low")   # GLM-5.x: low | high | max
    glm_search_engine: str = os.getenv("GLM_SEARCH_ENGINE", "search_pro_quark")
    finnhub_key: str = os.getenv("FINNHUB_KEY", "")
    tushare_token: str = os.getenv("TUSHARE_TOKEN", "")
    sec_contact: str = os.getenv("SEC_CONTACT", "")
    db_path: Path = ROOT / os.getenv("LANTERN_DB", "backend/data/lantern.db")

    @property
    def llm_enabled(self) -> bool:
        return bool(self.glm_api_key)


settings = Settings()
