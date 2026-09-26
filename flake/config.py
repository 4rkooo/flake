import os
from dotenv import load_dotenv
from pymongo import MongoClient
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

load_dotenv()

client = MongoClient(os.environ["MONGODB_URI"])
db = client[os.environ.get("MONGODB_DB", "flake")]

llm = ChatOpenAI(
    model=os.environ["LLM_MODEL"],
    api_key=os.environ["OPENROUTER_API_KEY"],
    base_url="https://openrouter.ai/api/v1",
    temperature=0,
)

embedder = OpenAIEmbeddings(model="text-embedding-3-small",
                            api_key=os.environ["OPENAI_API_KEY"])

def embed(text: str) -> list[float]:
    return embedder.embed_query(text)

DEMO_SEED = int(os.environ.get("DEMO_SEED", "42"))