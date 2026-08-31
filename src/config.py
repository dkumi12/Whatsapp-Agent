import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from langchain_openai import ChatOpenAI

# Load .env file automatically
load_dotenv(override=True)

class Settings(BaseSettings):
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = "google/gemini-2.5-flash"
    CHROMA_PERSIST_DIR: str = "./data/chroma_db"
    COHORT_1_GROUP_ID: str = ""
    COHORT_2_GROUP_ID: str = ""
    FASTAPI_HOST: str = "0.0.0.0"
    PORT: int = 8080

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()

def get_llm(temperature: float = 0.0):
    # Retrieve key and model from environment or settings
    api_key = os.getenv("OPENROUTER_API_KEY") or settings.OPENROUTER_API_KEY
    model = os.getenv("OPENROUTER_MODEL") or settings.OPENROUTER_MODEL or "google/gemini-2.5-flash"
    
    if not api_key:
        print("⚠️ Warning: OPENROUTER_API_KEY is not set. Please create a .env file with OPENROUTER_API_KEY=sk-or-v1-...")

    return ChatOpenAI(
        model=model,
        api_key=api_key or "sk-or-dummy-key-placeholder",
        base_url="https://openrouter.ai/api/v1",
        temperature=temperature,
        default_headers={
            "HTTP-Referer": "https://github.com/bootcamp-copilot",
            "X-Title": "Cohort Prefect Copilot"
        }
    )
