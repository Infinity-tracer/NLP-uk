"""Track B - Clinical Summarization API endpoints."""
import os
import time
import json
import boto3
from fastapi import APIRouter, HTTPException

from api.config import settings
from api.schemas.requests import TrackBRequest
from api.schemas.responses import TrackBResponse

router = APIRouter()


def extract_text_from_textract(textract_data: dict) -> str:
    """Extract raw text from Textract JSON response."""
    text_lines = []
    for block in textract_data.get('Blocks', []):
        if block.get('BlockType') == 'LINE':
            text_lines.append(block.get('Text', ''))
    return " ".join(text_lines)


def generate_summary_with_bedrock(text: str) -> dict:
    """Generate clinical summary using AWS Bedrock (Claude)."""
    bedrock = boto3.client(
        'bedrock-runtime',
        region_name=settings.AWS_REGION
    )

    prompt = f"""You are a clinical documentation specialist. Analyze the following medical document text and provide:

1. A concise clinical summary (2-3 paragraphs)
2. Key findings (bullet points)
3. Action plans for:
   - Clinician
   - Patient
   - Pharmacist

Medical Document Text:
{text[:8000]}

Respond in JSON format:
{{
    "summary": "...",
    "key_findings": ["finding1", "finding2", ...],
    "action_plans": {{
        "clinician": ["action1", "action2"],
        "patient": ["action1", "action2"],
        "pharmacist": ["action1", "action2"]
    }}
}}"""

    try:
        response = bedrock.invoke_model(
            modelId="us.anthropic.claude-sonnet-4-20250514-v1:0",
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 2000,
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            })
        )

        response_body = json.loads(response['body'].read())
        assistant_message = response_body['content'][0]['text']

        # Parse JSON from response
        # Handle case where response might have markdown code blocks
        if "```json" in assistant_message:
            json_start = assistant_message.find("```json") + 7
            json_end = assistant_message.find("```", json_start)
            assistant_message = assistant_message[json_start:json_end]
        elif "```" in assistant_message:
            json_start = assistant_message.find("```") + 3
            json_end = assistant_message.find("```", json_start)
            assistant_message = assistant_message[json_start:json_end]

        return json.loads(assistant_message.strip())

    except json.JSONDecodeError:
        # If JSON parsing fails, return raw summary
        return {
            "summary": assistant_message if 'assistant_message' in dir() else "Summary generation failed",
            "key_findings": [],
            "action_plans": {"clinician": [], "patient": [], "pharmacist": []}
        }
    except Exception as e:
        raise Exception(f"Bedrock summarization error: {str(e)}")


@router.post("/summarize", response_model=TrackBResponse)
async def summarize_document(request: TrackBRequest):
    """
    Track B: Clinical Summarization

    Uses AWS Bedrock (Claude) to generate:
    - Clinical summary
    - Key findings
    - Role-based action plans (Clinician, Patient, Pharmacist)

    Accepts either:
    - textract_json_path: Path to Textract output file
    - text: Raw text to summarize
    """
    start_time = time.time()

    # Get text to summarize
    text_to_summarize = None

    if request.text:
        text_to_summarize = request.text
    elif request.textract_json_path:
        if not os.path.exists(request.textract_json_path):
            raise HTTPException(
                status_code=404,
                detail=f"Textract file not found: {request.textract_json_path}"
            )
        with open(request.textract_json_path, 'r') as f:
            textract_data = json.load(f)
        text_to_summarize = extract_text_from_textract(textract_data)
    else:
        raise HTTPException(
            status_code=400,
            detail="Either 'text' or 'textract_json_path' must be provided"
        )

    if not text_to_summarize or not text_to_summarize.strip():
        raise HTTPException(
            status_code=400,
            detail="No text to summarize"
        )

    try:
        result = generate_summary_with_bedrock(text_to_summarize)

        processing_time = int((time.time() - start_time) * 1000)

        return TrackBResponse(
            status="success",
            summary=result.get("summary", ""),
            key_findings=result.get("key_findings", []),
            action_plans=result.get("action_plans", {}),
            processing_time_ms=processing_time,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Summarization error: {str(e)}"
        )


@router.post("/summarize-simple")
async def summarize_simple(text: str):
    """
    Track B: Simple text summarization endpoint.

    Quick endpoint for testing - just pass text directly.
    """
    start_time = time.time()

    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="No text provided")

    try:
        result = generate_summary_with_bedrock(text)
        processing_time = int((time.time() - start_time) * 1000)

        return {
            "status": "success",
            "summary": result.get("summary", ""),
            "key_findings": result.get("key_findings", []),
            "action_plans": result.get("action_plans", {}),
            "processing_time_ms": processing_time,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Summarization error: {str(e)}"
        )
