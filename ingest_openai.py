import os
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
VECTOR_STORE_ID = os.getenv("VECTOR_STORE_ID")

FOLDER_PATHS = ["laws", "data"]
ALLOWED_EXTENSIONS = {".pdf", ".txt"}


def upload_files_from_folders(folder_paths):
    file_ids = []
    base_dir = Path(__file__).resolve().parent

    for folder_path in folder_paths:
        full_folder = base_dir / folder_path
        if not full_folder.is_dir():
            print(f"Skipped missing folder: {folder_path}")
            continue

        for file_path in full_folder.iterdir():
            if not file_path.is_file():
                continue
            if file_path.name.startswith("."):
                continue
            if file_path.suffix.lower() not in ALLOWED_EXTENSIONS:
                print(f"Skipped unsupported file: {file_path.name}")
                continue

            try:
                with open(file_path, "rb") as f:
                    uploaded = client.files.create(
                        file=f,
                        purpose="assistants",
                    )
                print(f"Uploaded: {file_path.name} -> {uploaded.id}")
                file_ids.append(uploaded.id)
            except Exception as e:
                print(f"Failed: {file_path.name} -> {e}")

    return file_ids


def main():
    file_ids = upload_files_from_folders(FOLDER_PATHS)

    if not file_ids:
        print("No files uploaded.")
        return

    if VECTOR_STORE_ID:
        vector_store_id = VECTOR_STORE_ID
        print(f"Using existing Vector Store ID: {vector_store_id}")
    else:
        vector_store = client.vector_stores.create(
            name="unified-medical-legal-store",
        )
        vector_store_id = vector_store.id
        print(f"Created Vector Store ID: {vector_store_id}")
        print("Add this value to .env as VECTOR_STORE_ID")

    batch = client.vector_stores.file_batches.create(
        vector_store_id=vector_store_id,
        file_ids=file_ids,
    )

    print(f"Batch ID: {batch.id}")
    print(f"Batch Status: {batch.status}")


if __name__ == "__main__":
    main()