from __future__ import annotations

import base64
import os
from typing import AsyncIterable

import requests
import json
from fastapi_poe import PoeBot, make_app
from fastapi_poe.client import MetaMessage, stream_request
from fastapi_poe.types import (
    PartialResponse,
    ProtocolMessage,
    QueryRequest,
    SettingsRequest,
    SettingsResponse,
)
from modal import App, Image, asgi_app

app = App("BoardBuddy")

INTRODUCTION_MESSAGE = """
Take a picture of your whiteboard draft. This bot will create documentation from the picture.
Upload a picture to start.
""".strip()


# def format_utc_date():
#     utc_now = datetime.utcnow()
#     formatted_date = utc_now.strftime("%Y_%m_%d")
#     return formatted_date

def format_pacific_time():
    # pacific_tz = pytz.timezone('America/Los_Angeles')
    # pacific_now = datetime.now(pacific_tz)
    # formatted_time = pacific_now.strftime("%Y-%m-%d %H:%M PDT")
    return "2024-08-17"


def create_notion_page(title: str, content: str):
    pdt_date_str = format_pacific_time()
    appended_title = f"{title} - {pdt_date_str}"

    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": "Bearer secret_pIiXBtHIANdRvGxXG88kH9jlfDNjUQHZffyGH7O2LGi",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    data = {
        "parent": {
            "database_id": "0373a85b79df401b82b48b4f136554d2"
        },
        "properties": {
            "title": {
                "title": [
                    {
                        "text": {
                            "content": appended_title
                        }
                    }
                ]
            }
        },
        "children": [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": content
                            }
                        }
                    ]
                }
            }
        ]
    }

    response = requests.post(url, headers=headers, data=json.dumps(data))

    if response.status_code == 200:
        print("Page created successfully.")
    else:
        print(f"Failed to create page. Status code: {response.status_code}")
        print(response.text)


def clean_up_notion_request(data: str):
    # todo Perhaps use this to clean up to HTML objects or some other format for
    prepend_str = f"This page is AI generated using Poe, Modal, GPT-4o, and BoardBuddy\n\n"
    return prepend_str + data


# Define the bot class
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

                # Extract the Mermaid code only
                mermaid_code = self.extract_mermaid_code(current_bot_reply)

                if mermaid_code:
                    mermaid_url = self.generate_mermaid_url(mermaid_code)
                    # Add the Mermaid diagram URL to the response
                    yield self.text_event(
                        f"\nYou can also view the diagram here: [Mermaid Chart]({mermaid_url})")
                else:
                    yield self.text_event(
                        "No valid Mermaid diagram code was found in the response.")

                # make call to Notion api to create new page
                create_notion_page("New Page", clean_up_notion_request(current_bot_reply + "\n\n" + mermaid_url))

        else:
            yield self.text_event("Please upload an image to proceed.")

    def extract_mermaid_code(self, response_text: str) -> str:
        # Extract the content between the ```mermaid and ``` delimiters
        start_marker = "```mermaid"
        end_marker = "```"
        start_idx = response_text.find(start_marker)
        end_idx = response_text.find(end_marker, start_idx + len(start_marker))
        if start_idx != -1 and end_idx != -1:
            # Extract and return the Mermaid code
            return response_text[start_idx + len(start_marker):end_idx].strip()
        return ""

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
