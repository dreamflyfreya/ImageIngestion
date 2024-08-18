from __future__ import annotations

import os
import requests
import base64
from typing import AsyncIterable

import modal
from modal import App, Image, asgi_app
from fastapi_poe import PoeBot, make_app
from fastapi_poe.types import (
    PartialResponse,
    QueryRequest,
    SettingsRequest,
    SettingsResponse,
)

app = App("BoardBuddy")

INTRODUCTION_MESSAGE = """
Take a picture of your whiteboard draft. This bot will create documentation from the picture.
Upload a picture to start.
""".strip()

# Function to extract the diagram and words from an image
def extract_image_details(image_path):
    # Placeholder for the actual image processing logic
    # Ideally, this could involve OCR for text extraction and some form of image analysis for diagrams
    # For now, we'll assume the function extracts words and a diagram (Mermaid code)
    
    # Example extraction results
    extracted_words = """
    Stack: PoE / firework
    
    Data capture types:
    - Presentation notes
    - Tech stack diagrams/descriptions
    - Code snippets/deploy scripts/config
    - Q&A for refinement/edits
    """
    
    mermaid_code = """
    graph TD
        PoE --> Model
        Model --> Fireworks
    """
    
    return extracted_words, mermaid_code

# Function to generate a Mermaid chart URL using a third-party service
def generate_mermaid_url(mermaid_code: str) -> str:
    # Encode the Mermaid code to base64
    base64_encoded_code = base64.urlsafe_b64encode(mermaid_code.encode('utf-8')).decode('utf-8')
    
    # Construct the URL
    url = f"https://mermaid.ink/svg/{base64_encoded_code}"
    
    return url

# Define the bot class
class ImageProcessingBot(PoeBot):
    allow_attachments = True  # Ensure this is set to True

    async def get_response(
        self, request: QueryRequest
    ) -> AsyncIterable[PartialResponse]:
        try:
            # Check for attachments
            if request.query[-1].attachments:
                for attachment in request.query[-1].attachments:
                    # Download the image
                    r = requests.get(attachment.url)
                    image_path = attachment.name
                    with open(image_path, "wb") as f:
                        f.write(r.content)

                    # Extract words and diagram from the image
                    extracted_words, mermaid_code = extract_image_details(image_path)

                    # Generate a Mermaid chart URL
                    mermaid_url = generate_mermaid_url(mermaid_code)

                    # Build the response
                    response_text = f"""
                    Extracted Words:
                    {extracted_words}

                    Mermaid Diagram Code:
                    ```mermaid
                    {mermaid_code}
                    ```

                    You can also view the diagram here: [Mermaid Chart]({mermaid_url})
                    """

                    yield self.text_event(response_text)
            else:
                # If no attachment is provided
                yield self.text_event("Please upload an image to proceed.")

        except Exception as e:
            # Catch any errors and return a friendly message
            yield self.text_event(f"An error occurred: {str(e)}")

    async def get_settings(self, setting: SettingsRequest) -> SettingsResponse:
        return SettingsResponse(
            server_bot_dependencies={self.prompt_bot: self.code_iteration_limit},
            allow_attachments=self.allow_attachments,
            introduction_message=INTRODUCTION_MESSAGE,
            enable_image_comprehension=True,
        )

# Setup the bot in the Modal environment
image_bot = (
    Image.debian_slim()
    .pip_install("fastapi-poe==0.0.43", "requests==2.28.2")
    .env(
        {
            "POE_ACCESS_KEY": os.environ["POE_ACCESS_KEY"],
        }
    )
)

bot = ImageProcessingBot()

@app.function(image=image_bot, container_idle_timeout=1200)
@asgi_app()
def fastapi_app():
    app = make_app(bot, api_key=os.environ["POE_ACCESS_KEY"])
    return app
