"""
Journalist Agent — local entrypoint for testing.

Usage:
    python agents/journalist/main.py

Make sure:
    1. Docker is running (NTP + News Website containers up)
    2. GEMINI_API_KEY is set in your .env file
    3. Knowledge docs are in agents/journalist/knowledge/
"""
import sys
import os

# Add project root to Python path so all modules are found
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from dotenv import load_dotenv
from agents.journalist.journalist_agent import JournalistAgent, JournalistConfig

load_dotenv()


def main():
    print("=" * 60)
    print("  Journalist Agent — The Daily Catch")
    print("  BitriX HappyTuna Crisis Simulation")
    print("=" * 60)

    # Load config from .env
    config = JournalistConfig.from_env()

    if not config.gemini_api_key:
        print("\n ERROR: GEMINI_API_KEY not set in .env file")
        return

    print(f"\n Model     : {config.model_name}")
    print(f" Embedding : {config.embedding_model}")  
    print(f" Max steps : {config.max_steps}")
    print(f" Chroma    : {config.chroma_persist_dir}")
    print(f" News URL  : {os.getenv('NEWS_URL', 'http://news-website:8003')}")

    with JournalistAgent(config) as agent:

        # Load knowledge base on first run
        print("\n Loading knowledge base...")
        agent.index_knowledge("agents/journalist/knowledge")

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