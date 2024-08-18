from __future__ import annotations
from typing import AsyncIterable
import requests
from PyPDF2 import PdfReader
import fastapi_poe as fp

from modal import App, Image, asgi_app, exit

class FileDownloadError(Exception):
    pass


def createNotionPage(title: str, content: str):
    content_block = {
        "parent": {
            "database_id": "0373a85b79df401b82b48b4f136554d2"
        },
        "properties": {
            "title": {
            "title": [
                {
                "text": {
                    "content": content
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
                    "content": "this is the sample text for Hello World #1"
                    }
                }
                ]
            }
            }
        ]
        }
    command = f'''
        curl -X POST https://api.notion.com/v1/pages -H "Authorization: Bearer secret_pIiXBtHIANdRvGxXG88kH9jlfDNjUQHZffyGH7O2LGi" \
        -H "Content-Type: application/json" -H "Notion-Version: 2022-06-28" -d "{content_block}"
    '''
    eval(command)


class ImageIngestion(fp.PoeBot):
    async def get_response(
        self, request: fp.QueryRequest
    ) -> AsyncIterable[fp.PartialResponse]:
        for message in reversed(request.query):
            for attachment in message.attachments:
                if attachment.content_type == "application/pdf":
                    try:
                        num_pages = _fetch_pdf_and_count_num_pages(attachment.url)
                        yield fp.PartialResponse(text=f"{attachment.name} has {num_pages} pages")
                    except FileDownloadError:
                        yield fp.PartialResponse(text="Failed to retrieve the document.")
                    return

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
        bot = PDFSizeBot()
        app = fp.make_app(bot, access_key=self.access_key)
        return app

@app.local_entrypoint()
def main():
    Model().run.remote()