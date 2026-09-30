import os
from dotenv import load_dotenv
from pymongo import MongoClient
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from flake import llmcache

load_dotenv()

client = MongoClient(os.environ["MONGODB_URI"])
db = client[os.environ.get("MONGODB_DB", "flake")]

llm = ChatOpenAI(
    model=os.environ["LLM_MODEL"],
    api_key=os.environ["OPENROUTER_API_KEY"],
    base_url="https://openrouter.ai/api/v1",
    temperature=0,
    # without a cap, OpenRouter reserves the model's full output limit (65k tokens) per call,
    # which a low credit balance rejects with 402; tool calls and proposals fit easily in this
    max_tokens=int(os.environ.get("LLM_MAX_TOKENS", "1024")),
)

embedder = OpenAIEmbeddings(model="text-embedding-3-small",
                            api_key=os.environ["OPENAI_API_KEY"])

def embed(text: str) -> list[float]:
    return embedder.embed_query(text)

DEMO_SEED = int(os.environ.get("DEMO_SEED", "42"))

# Identical calls replay from disk instead of the paid API. LLM_CACHE=0 turns it off.
LLM_CACHE_PATH = llmcache.install()

