from __future__ import annotations

import base64
import os
from typing import AsyncIterable

import openai
import pytz
import requests
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


def format_utc_date():
    utc_now = datetime.utcnow()
    formatted_date = utc_now.strftime("%Y_%m_%d")
    return formatted_date

def format_pacific_time():
    pacific_tz = pytz.timezone('America/Los_Angeles')
    pacific_now = datetime.now(pacific_tz)
    formatted_time = pacific_now.strftime("%Y-%m-%d %H:%M PDT")
    return formatted_time


def createNotionPage(title: str, content: str):
    pdt_date_str = format_pacific_time()
    appended_title = f"{title} - {pdt_date_str}"
    content_block = {
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
    response = openai.ChatCompletion.create(
        model="gpt-4-turbo",
        messages=[
            {"role": "system", "content": "You are a json generator. For any command, \
             you should only generate json and nothing else. \
             That is, you response should only contaion the resulting json string"},
            {"role": "user",
             "content": f"Please convert {str(content_block)} to notion readable json."}
        ]
    )
    print(response['choices'][0]['message']['content'])
    content_json = json.load(response['choices'][0]['message']['content'])
    command = f'''
        curl -X POST https://api.notion.com/v1/pages -H "Authorization: Bearer secret_pIiXBtHIANdRvGxXG88kH9jlfDNjUQHZffyGH7O2LGi" \
        -H "Content-Type: application/json" -H "Notion-Version: 2022-06-28" -d "{content_json}"
    '''
    eval(command)


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
                    yield self.text_event(f"\nYou can also view the diagram here: [Mermaid Chart]({mermaid_url})")
                else:
                    yield self.text_event("No valid Mermaid diagram code was found in the response.")

                # make call to Notion api to create new page
                createNotionPage("New Page", clean_up_notion_request(current_bot_reply))

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
