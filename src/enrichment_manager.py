# src/enrichment_manager.py
import json
import logging
import os
import time

from qdrant_client import QdrantClient
from qdrant_client.http.models import FieldCondition, Filter, MatchValue
from src.config import settings
from src.embeddings.client import EmbeddingClient
from src.embeddings.models import get_model_meta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("EnrichmentManager")

# Initialize Clients
qdrant_client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)

embed_client = EmbeddingClient(
    api_key=settings.TOGETHER_API_KEY,
    base_url=settings.TOGETHER_BASE_URL,
    model=settings.TOGETHER_EMBEDDING_MODEL,
)


SUMMARY_PROMPT_TEMPLATE = """You are a forensic analyst. Summarize the extracted text accurately. 
Focus on key events, entities (people, IPs, locations), and critical artifacts.

Text: {text}

Forensic Summary:"""


def prepare_batch_input(collection_name: str, limit=45000):
    """Extracts PENDING records and creates a JSONL input file."""
    filter_ = Filter(
        must=[FieldCondition(key="forensic_summary", match=MatchValue(value="PENDING"))]
    )

    # Use Qdrant's scroll API to fetch records
    records, _ = qdrant_client.scroll(
        collection_name=collection_name,
        scroll_filter=filter_,
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )

    if not records:
        return None, 0

    timestamp = int(time.time())
    input_filename = os.path.join(
        settings.BATCH_PROCESSING_DIR, f"batch_{timestamp}_input.jsonl"
    )

    with open(input_filename, "w") as f:
        for record in records:
            # Use Qdrant Point ID as the custom_id for tracking
            custom_id = str(record.id)
            text = record.payload.get("text", "")[:30000]  # Truncate for context limits

            # Format according to Together.AI Batch API schema
            batch_request = {
                "custom_id": custom_id,
                "body": {
                    "model": settings.ENRICHMENT_LLM_MODEL,
                    "messages": [
                        {
                            "role": "user",
                            "content": SUMMARY_PROMPT_TEMPLATE.format(text=text),
                        }
                    ],
                    "max_tokens": 512,
                },
            }
            f.write(json.dumps(batch_request) + "\n")

    return input_filename, len(records)


def submit_batch_job(input_filename: str):
    """Uploads the file and submits the Together.AI Batch job."""
    try:
        logger.info(
            f"Uploading {input_filename} to Together.AI (Purpose: batch-api)..."
        )
        file_resp = together_client.files.upload(
            file=input_filename, purpose="batch-api"
        )
        logger.info(f"Submitting Batch Job for File ID: {file_resp.id}")
        batch = together_client.batches.create_batch(
            file_resp.id, endpoint="/v1/chat/completions"
        )
        return batch.id
    except Exception as e:
        logger.error(f"Failed to submit batch job: {e}", exc_info=True)
        return None


def update_qdrant_with_summaries(output_filename: str, collection_name: str):
    """Reads the output JSONL and updates Qdrant."""
    updated_count = 0
    with open(output_filename, "r") as f:
        for line in f:
            result = json.loads(line)
            qdrant_point_id = result.get("custom_id")
            try:
                # Extract summary from the Chat Completion response
                summary = result["response"]["body"]["choices"][0]["message"]["content"]
                # Update the record in Qdrant
                qdrant_client.set_payload(
                    collection_name=collection_name,
                    payload={"forensic_summary": summary},
                    points=[qdrant_point_id],
                )
                updated_count += 1
            except (KeyError, TypeError, IndexError):
                logger.warning(
                    f"Could not extract summary for ID {qdrant_point_id}. Check error file if available."
                )
                # Update status if extraction fails
                qdrant_client.set_payload(
                    collection_name=collection_name,
                    payload={"forensic_summary": "ENRICHMENT_FAILED"},
                    points=[qdrant_point_id],
                )
    logger.info(f"Successfully updated {updated_count} records.")


def monitor_and_process_job(job_id: str, collection_name: str):
    """Monitors the job, downloads results, and updates Qdrant."""
    while True:
        batch_stat = together_client.batches.get_batch(job_id)
        # Handle potential AttributeError if progress isn't immediately available
        progress = getattr(batch_stat, "progress", "N/A")
        logger.info(f"Job {job_id} Status: {batch_stat.status} (Progress: {progress}%)")

        if batch_stat.status == "COMPLETED":
            timestamp = int(time.time())
            output_filename = os.path.join(
                settings.BATCH_PROCESSING_DIR, f"batch_{timestamp}_output.jsonl"
            )
            logger.info("Downloading results...")
            together_client.files.retrieve_content(
                id=batch_stat.output_file_id, output=output_filename
            )
            update_qdrant_with_summaries(output_filename, collection_name)
            break
        elif batch_stat.status in ["FAILED", "EXPIRED", "CANCELLED"]:
            logger.error(f"Batch job terminated: {batch_stat.status}")
            # Implement logic here to handle failed batches (e.g., retry or mark records as failed)
            break

        time.sleep(300)  # Poll every 5 minutes


def run_orchestrator():
    """Main loop for the Enrichment Manager (Pipeline B)."""
    COLLECTION = settings.QDRANT_COLLECTION
    logger.info("Enrichment Manager Started. Monitoring Qdrant for PENDING records...")

    # Ensure the batch processing directory exists
    os.makedirs(settings.BATCH_PROCESSING_DIR, exist_ok=True)

    while True:
        try:
            # 1. Prepare Input
            input_file, count = prepare_batch_input(COLLECTION)
            if input_file:
                logger.info(f"Found {count} records. Preparing Batch Job...")
                # 2. Submit Job
                job_id = submit_batch_job(input_file)
                if job_id:
                    logger.info(
                        f"Submitted Together.AI Batch Job ID: {job_id}. Waiting for results (may take hours)..."
                    )
                    # 3. Process Results (Blocking call until this specific job finishes)
                    monitor_and_process_job(job_id, COLLECTION)
            else:
                logger.info("No PENDING records found. Sleeping for 15 minutes...")
                time.sleep(900)
        except Exception as e:
            logger.error(f"Error in orchestration loop: {e}", exc_info=True)
            time.sleep(60)


if __name__ == "__main__":
    run_orchestrator()
