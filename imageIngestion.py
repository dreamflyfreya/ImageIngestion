from __future__ import annotations
from typing import AsyncIterable
import requests
from PyPDF2 import PdfReader
import fastapi_poe as fp

from modal import App, Image, asgi_app, exit

import openai
import json
# Replace with your OpenAI API key
openai.api_key = "your-api-key"

# Call the GPT-4 API (gpt-4-turbo)

# Print the assistant's reply

class FileDownloadError(Exception):
    pass

def format_utc_date():
    utc_now = datetime.utcnow()
    formatted_date = utc_now.strftime("%Y_%m_%d")
    return formatted_date

def createNotionPage(title: str, content: str):
    utc_date_str = format_utc_date()
    appended_title = f"{title} - {utc_date_str}"
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
            {"role": "user", "content": f"Please convert {str(content_block)} to notion readable json."}
        ]
    )
    print(response['choices'][0]['message']['content'])
    content_json = json.load(response['choices'][0]['message']['content'])
    command = f'''
        curl -X POST https://api.notion.com/v1/pages -H "Authorization: Bearer secret_pIiXBtHIANdRvGxXG88kH9jlfDNjUQHZffyGH7O2LGi" \
        -H "Content-Type: application/json" -H "Notion-Version: 2022-06-28" -d "{content_json}"
    '''
    eval(command)


class ImageIngestion(fp.PoeBot):
    async def get_response(
        self, request: fp.QueryRequest
    ) -> AsyncIterable[fp.PartialResponse]:

        async for msg in fp.stream_request(
            request, "GPT-4o", request.access_key
        ):
            full_response.append(msg)
        full_response = ''.join(full_response)
        createNotionPage("hello world", full_response)

    async def get_settings(self, setting: fp.SettingsRequest) -> fp.SettingsResponse:
        return fp.SettingsResponse(allow_attachments=True)
    

# =============== MODAL CODE TO RUN THE BOT ================== #
REQUIREMENTS = ["fastapi-poe==0.0.47", "PyPDF2==3.0.1", "requests==2.31.0"]
image = Image.debian_slim().pip_install(*REQUIREMENTS)
app = App(name="pdf-counter-poe", image=image)

@app.cls()
class Model:
    access_key: str | None = None  # REPLACE WITH YOUR ACCESS KEY
    bot_name: str | None = None  # REPLACE WITH YOUR BOT NAME
    
    @exit()
    def sync_settings(self):
        """Syncs bot settings on server shutdown."""
        if self.bot_name and self.access_key:
            fp.sync_bot_settings(self.bot_name, self.access_key)
            
    @asgi_app()
    def fastapi_app(self):
        bot = ImageIngestion()
        app = fp.make_app(bot, access_key=self.access_key)
        return app

@app.local_entrypoint()
def main():
    Model().run.remote()