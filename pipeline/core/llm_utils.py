import os
import base64
import time
from openai import OpenAI
from .config import N1N_API_KEY, N1N_BASE_URL

client = OpenAI(
    api_key=N1N_API_KEY,
    base_url=N1N_BASE_URL
)

REQUEST_TIMEOUT = float(os.environ.get("MDR_TIMEOUT_SECONDS", "300"))
REQUEST_TEMPERATURE = float(os.environ.get("MDR_TEMPERATURE", "0.7"))
REQUEST_RETRIES = int(os.environ.get("MDR_RETRIES", "3"))
REQUEST_RETRY_SLEEP = float(os.environ.get("MDR_RETRY_SLEEP_SECONDS", "2"))

def _collect_stream_text(stream):
    parts = []
    for chunk in stream:
        if not getattr(chunk, "choices", None):
            continue
        delta = getattr(chunk.choices[0], "delta", None)
        content = getattr(delta, "content", None)
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if text:
                        parts.append(text)
    return "".join(parts)

def chat_with_model(model_name, system_prompt, user_prompt, max_tokens=4000):
    print(f"--- Calling model {model_name} ---")
    last_error = None
    for attempt in range(1, REQUEST_RETRIES + 1):
        try:
            stream = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=max_tokens,
                temperature=REQUEST_TEMPERATURE,
                timeout=REQUEST_TIMEOUT,
                stream=True,
            )
            return _collect_stream_text(stream)
        except Exception as e:
            last_error = e
            print(f"Error calling model (attempt {attempt}/{REQUEST_RETRIES}): {e}")
            if attempt < REQUEST_RETRIES:
                time.sleep(REQUEST_RETRY_SLEEP * attempt)
    print(f"Error calling model: {last_error}")
    return ""

def chat_with_image(model_name, system_prompt, user_prompt, image_path, max_tokens=4000):
    print(f"--- Calling MLLM {model_name} with image {image_path} ---")
    last_error = None
    for attempt in range(1, REQUEST_RETRIES + 1):
        try:
            with open(image_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')
            
            mime_type = "image/jpeg"
            if image_path.lower().endswith('.png'):
                mime_type = "image/png"
                
            stream = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=max_tokens,
                temperature=REQUEST_TEMPERATURE,
                timeout=REQUEST_TIMEOUT,
                stream=True,
            )
            return _collect_stream_text(stream)
        except Exception as e:
            last_error = e
            print(f"Error calling MLLM (attempt {attempt}/{REQUEST_RETRIES}): {e}")
            if attempt < REQUEST_RETRIES:
                time.sleep(REQUEST_RETRY_SLEEP * attempt)
    print(f"Error calling MLLM: {last_error}")
    return ""
