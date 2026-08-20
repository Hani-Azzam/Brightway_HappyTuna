"""
Journalist Agent — interactive local entrypoint for testing.

Usage (from agents/journalist/):
    python main.py

Make sure:
    1. The journalism-site and chroma containers are up (see repo-root docker-compose.yml)
    2. GEMINI_API_KEY is set in the repo-root .env file
    3. Knowledge docs are in knowledge/
"""
import os

from dotenv import load_dotenv
from journalist_agent import JournalistAgent, JournalistConfig

load_dotenv()


def main():
    print("=" * 60)
    print("  Journalist Agent — The Daily Catch")
    print("  BitriX HappyTuna Crisis Simulation")
    print("=" * 60)

    # Load config from .env
    config = JournalistConfig.from_env()

    # Two keys, two jobs: Claude Haiku reasons, Gemini embeds the knowledge base
    # (Anthropic has no embeddings API). Either one missing is fatal, so name the
    # one that's missing instead of failing later inside the RAG pipeline.
    if not config.anthropic_api_key:
        print("\n ERROR: ANTHROPIC_API_KEY not set in .env file (the reasoning model)")
        return

    if not config.gemini_api_key:
        print("\n ERROR: GEMINI_API_KEY not set in .env file (knowledge-base embeddings)")
        return

    print(f"\n Model     : {config.model_name}")
    print(f" Embedding : {config.embedding_model}")  
    print(f" Max steps : {config.max_steps}")
    print(f" Chroma    : {config.chroma_persist_dir}")
    print(f" News URL  : {os.getenv('NEWS_URL', 'http://journalism-site:8003')}")

    with JournalistAgent(config) as agent:

        # Load knowledge base on first run
        print("\n Loading knowledge base...")
        agent.index_knowledge("knowledge")

        print("\n Agent ready. Type a news event or 'quit' to exit.")
        print(" Example: 'salmonella detected at HappyTuna Production Line A'\n")

        while True:
            try:
                user_input = input("Event > ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nShutting down.")
                break

            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "q"):
                print("Shutting down.")
                break

            print("\n Journalist is investigating...\n")
            response = agent.chat(user_input)
            print(f"\n Agent: {response}\n")
            print("-" * 60)


if __name__ == "__main__":
    main()