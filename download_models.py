#!/usr/bin/env python3
"""
Download required models before starting the server
"""

import os
from pathlib import Path
from huggingface_hub import snapshot_download
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "jinaai/jina-embeddings-v3")
LLM_MODEL = os.getenv("LLM_MODEL", "mlx-community/Qwen3-30B-A3B-4bit")
MODEL_DIR = Path(os.getenv("MODEL_DIR", "./model"))

# Create model directory
MODEL_DIR.mkdir(parents=True, exist_ok=True)

def download_model(model_name: str, model_type: str):
    """Download a model from HuggingFace"""
    print(f"\n{'='*60}")
    print(f"📥 Downloading {model_type}: {model_name}")
    print(f"{'='*60}")

    # Convert model name to safe directory name
    safe_name = model_name.replace("/", "--")
    local_path = MODEL_DIR / safe_name

    # Check if model already exists
    if local_path.exists() and any(local_path.iterdir()):
        print(f"✅ Model already exists: {local_path}")
        return str(local_path)

    try:
        print(f"📦 Downloading to: {local_path}")
        print("⏳ This may take several minutes...")

        snapshot_download(
            repo_id=model_name,
            local_dir=str(local_path),
            local_dir_use_symlinks=False,
            resume_download=True,
        )

        print(f"✅ Successfully downloaded: {model_name}")
        return str(local_path)
    except Exception as e:
        print(f"❌ Failed to download {model_name}: {e}")
        raise

def main():
    print("🚀 Model Download Script")
    print(f"📁 Model directory: {MODEL_DIR.absolute()}\n")

    models = [
        (EMBEDDING_MODEL, "Embedding Model"),
        (LLM_MODEL, "LLM Model"),
    ]

    for model_name, model_type in models:
        try:
            download_model(model_name, model_type)
        except Exception as e:
            print(f"\n⚠️  Warning: Could not download {model_name}")
            print(f"   Error: {e}")
            print("   The model will be downloaded automatically when the server starts.\n")
            continue

    print("\n" + "="*60)
    print("✨ Model download completed!")
    print("="*60)
    print("\n📊 Downloaded models:")

    for item in MODEL_DIR.iterdir():
        if item.is_dir():
            size = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
            size_gb = size / (1024**3)
            print(f"  • {item.name}: {size_gb:.2f} GB")

    print("\n🚀 You can now start the server with: ./run.sh")

if __name__ == "__main__":
    main()
