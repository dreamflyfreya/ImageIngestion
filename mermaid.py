import base64
import urllib.parse

def generate_mermaid_url(mermaid_code: str) -> str:
    # Encode the Mermaid code to base64
    base64_encoded_code = base64.urlsafe_b64encode(mermaid_code.encode('utf-8')).decode('utf-8')
    
    # Construct the URL
    url = f"https://mermaid.ink/svg/{base64_encoded_code}"
    
    return url

# Example Mermaid code
mermaid_code = """
flowchart TD

A([PoE]) --> B[Model]
B --> C[Fireworks]
"""

# Generate the URL
url = generate_mermaid_url(mermaid_code)
print("Mermaid Chart URL:", url)
