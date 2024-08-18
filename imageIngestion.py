from __future__ import annotations

from typing import AsyncIterable

import fastapi_poe as fp
import openai

# Replace with your OpenAI API key
openai.api_key = "your-api-key"

# Call the GPT-4 API (gpt-4-turbo)

# Print the assistant's reply

class FileDownloadError(Exception):
    pass




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
    
