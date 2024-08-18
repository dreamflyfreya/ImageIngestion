from __future__ import annotations

import os
import requests
import base64
from typing import AsyncIterable

import modal
from modal import App, Image, asgi_app
from fastapi_poe import PoeBot, make_app
from fastapi_poe.client import MetaMessage, stream_request
from fastapi_poe.types import (
    Attachment,
    PartialResponse,
    ProtocolMessage,
    QueryRequest,
    SettingsRequest,
    SettingsResponse,
)

app = App("BoardBuddy")

INTRODUCTION_MESSAGE = """
Take a picture of your whiteboard draft. This bot will create documentation from the picture.
Upload a picture to start.
""".strip()


class ImageProcessingBot(PoeBot):
    prompt_bot = "GPT-4o"  # Using GPT-4o for generating responses
    allow_attachments = True  # Ensure this is set to True

    async def get_response(
        self, request: QueryRequest
    ) -> AsyncIterable[PartialResponse]:
        last_message = request.query[-1].content
        original_message_id = request.message_id

        # Check if there are attachments (images)
        if request.query[-1].attachments:
            for attachment in request.query[-1].attachments:
                # Download the image
                r = requests.get(attachment.url)
                image_path = attachment.name
                with open(image_path, "wb") as f:
                    f.write(r.content)

                # Prepare prompt for GPT-4o
                prompt = f"""
                I have an image with the file path: {image_path}. 
                Please analyze the image and extract any text and diagram details. 
                Return the extracted text and convert any diagrams into Mermaid diagram code.
                """

                # Add the prompt to the request and call GPT-4o
                request.query.append(ProtocolMessage(role="user", content=prompt))
                current_bot_reply = ""

                async for msg in stream_request(request, self.prompt_bot, request.api_key):
                    if isinstance(msg, MetaMessage):
                        continue
                    elif msg.is_suggested_reply:
                        yield self.suggested_reply_event(msg.text)
                    elif msg.is_replace_response:
                        yield self.replace_response_event(msg.text)
                    else:
                        current_bot_reply += msg.text
                        yield self.text_event(msg.text)

                # If you want to further process or extract specific parts of the response, you can do it here.
                # For instance, extract Mermaid code and generate a URL.
                if "```mermaid" in current_bot_reply:
                    mermaid_code = current_bot_reply.split("```mermaid")[1].strip("```")
                    mermaid_url = self.generate_mermaid_url(mermaid_code)

                    # Add the Mermaid diagram URL to the response
                    yield self.text_event(f"\nYou can also view the diagram here: [Mermaid Chart]({mermaid_url})")
        else:
            yield self.text_event("Please upload an image to proceed.")

    def generate_mermaid_url(self, mermaid_code: str) -> str:
        # Encode the Mermaid code to base64
        base64_encoded_code = base64.urlsafe_b64encode(mermaid_code.encode('utf-8')).decode('utf-8')
        # Construct the URL
        return f"https://mermaid.ink/svg/{base64_encoded_code}"

    async def get_settings(self, setting: SettingsRequest) -> SettingsResponse:
        return SettingsResponse(
            allow_attachments=self.allow_attachments,
            introduction_message=INTRODUCTION_MESSAGE,
            enable_image_comprehension=True,
            server_bot_dependencies={self.prompt_bot: 3},  # Allow 3 calls to GPT-4o
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
