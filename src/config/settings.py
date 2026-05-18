import sys
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent.parent


class _Settings:
    def __init__(self):
        self.project_root: Path = PROJECT_ROOT
        self._load()

    def _load(self):
        self.openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
        self.openrouter_base_url: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        self.model_name: str = os.getenv("MODEL_NAME", "openai/gpt-4o")

        self.gitlab_url: str = os.getenv("GITLAB_URL", "https://gitlab.com")
        self.gitlab_token: str = os.getenv("GITLAB_TOKEN", "")

        self.vector_database_url: str = os.getenv("VECTOR_DATABASE_URL", "")

        self.postman_api_key: str = os.getenv("POSTMAN_API_KEY", "").strip()
        self.postman_workspace_id: str = os.getenv("POSTMAN_WORKSPACE_ID", "").strip()
        self.postman_collection_json: str = os.getenv("POSTMAN_COLLECTION_JSON", "").strip()
        self.postman_cache_dir: Path = Path(os.getenv("POSTMAN_CACHE_DIR", "./postman_cache"))
        self.postman_cache_ttl: int = 3600

        self.android_project_root: str = os.getenv("ANDROID_PROJECT_ROOT", "").strip()

        self.figma_mcp_url: str = os.getenv("FIGMA_MCP_URL", "http://127.0.0.1:3845/sse")

        self.rag_collection_name: str = os.getenv("RAG_COLLECTION_NAME", "company_guidelines")
        self.rag_embedding_model: str = os.getenv("RAG_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

        self._validate()

    def _validate(self):
        if not self.openrouter_api_key:
            print("[WARNING] OPENROUTER_API_KEY belum diset.", file=sys.stderr)

    def create_llm_config(self) -> dict:
        return {
            "model": self.model_name,
            "api_key": self.openrouter_api_key,
            "base_url": self.openrouter_base_url,
        }


settings = _Settings()