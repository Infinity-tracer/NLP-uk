"""Test script to debug Tier 3 Vision-LLM Bedrock call."""
import boto3
import json
import base64
import io
from PIL import Image

# Create a simple test image (red rectangle with text area)
def create_test_image():
    img = Image.new('RGB', (200, 50), color=(255, 255, 255))
    return img

def test_bedrock_vision():
    print("=" * 60)
    print("Testing Bedrock Vision Call for Tier 3")
    print("=" * 60)

    # Create Bedrock client
    bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

    # Create test image and encode to base64
    test_image = create_test_image()
    buffer = io.BytesIO()
    test_image.save(buffer, format='PNG')
    buffer.seek(0)
    b64_image = base64.standard_b64encode(buffer.read()).decode('utf-8')

    print(f"Test image size: {test_image.size}")
    print(f"Base64 length: {len(b64_image)}")

    # Model ID - the same one used in tier3 config
    model_id = "us.anthropic.claude-sonnet-4-20250514-v1:0"
    print(f"Model ID: {model_id}")

    # Build request with vision
    request_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 512,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64_image,
                        },
                    },
                    {
                        "type": "text",
                        "text": "What do you see in this image? Reply in JSON format: {\"description\": \"...\"}",
                    },
                ],
            }
        ],
    }

    print("\nSending vision request to Bedrock...")

    try:
        response = bedrock.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(request_body),
        )

        raw_body = response["body"].read().decode("utf-8")
        response_data = json.loads(raw_body)

        print("\n[SUCCESS] Response:")
        print(json.dumps(response_data, indent=2))

        # Extract text
        content_blocks = response_data.get("content", [])
        for block in content_blocks:
            if block.get("type") == "text":
                print(f"\nModel response text: {block['text']}")

        return True

    except Exception as e:
        print(f"\n[FAIL] FAILED! Error: {type(e).__name__}")
        print(f"Error message: {str(e)}")

        # Try to get more details
        if hasattr(e, 'response'):
            print(f"Response: {e.response}")

        return False


def test_alternative_models():
    """Try different model IDs to find one that works with vision."""

    models_to_try = [
        "us.anthropic.claude-sonnet-4-20250514-v1:0",
        "anthropic.claude-3-5-sonnet-20241022-v2:0",
        "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
        "anthropic.claude-3-sonnet-20240229-v1:0",
        "us.anthropic.claude-3-sonnet-20240229-v1:0",
    ]

    bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

    # Create test image
    test_image = create_test_image()
    buffer = io.BytesIO()
    test_image.save(buffer, format='PNG')
    buffer.seek(0)
    b64_image = base64.standard_b64encode(buffer.read()).decode('utf-8')

    print("\n" + "=" * 60)
    print("Testing multiple model IDs for vision support")
    print("=" * 60)

    for model_id in models_to_try:
        print(f"\nTrying: {model_id}")

        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 100,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64_image,
                            },
                        },
                        {
                            "type": "text",
                            "text": "Describe this image in one sentence.",
                        },
                    ],
                }
            ],
        }

        try:
            response = bedrock.invoke_model(
                modelId=model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(request_body),
            )
            raw_body = response["body"].read().decode("utf-8")
            print(f"  [OK] SUCCESS with {model_id}")
            return model_id

        except Exception as e:
            error_msg = str(e)[:100]
            print(f"  [FAIL] Failed: {error_msg}")

    print("\nNo working vision model found!")
    return None


if __name__ == "__main__":
    # First test the current model
    success = test_bedrock_vision()

    if not success:
        # Try to find a working model
        print("\n\nSearching for a working vision model...")
        working_model = test_alternative_models()

        if working_model:
            print(f"\n\n[FOUND] Found working vision model: {working_model}")
            print("Update tier3_ocr_correction/config.py with this model ID")
