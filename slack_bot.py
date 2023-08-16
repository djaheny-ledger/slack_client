from fastapi import FastAPI, Request, Response
from slack_sdk import WebClient
from slack_sdk.signature import SignatureVerifier
from pydantic import BaseModel
import os
import requests
import json
from dotenv import main
from nltk.tokenize import word_tokenize
import re
import nltk
if not nltk.data.find('tokenizers/punkt'):
    nltk.download('punkt')


# Initialize the FastAPI app
app = FastAPI()

# Secret Management
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")
BACKEND_API_KEY = os.getenv("BACKEND_API_KEY")


ETHEREUM_ADDRESS_PATTERN = r'\b0x[a-fA-F0-9]{40}\b'
BITCOIN_ADDRESS_PATTERN = r'\b(1|3)[1-9A-HJ-NP-Za-km-z]{25,34}\b|bc1[a-zA-Z0-9]{25,90}\b'
LITECOIN_ADDRESS_PATTERN = r'\b(L|M)[a-km-zA-HJ-NP-Z1-9]{26,34}\b'
DOGECOIN_ADDRESS_PATTERN = r'\bD{1}[5-9A-HJ-NP-U]{1}[1-9A-HJ-NP-Za-km-z]{32}\b'
XRP_ADDRESS_PATTERN = r'\br[a-zA-Z0-9]{24,34}\b'

with open('bip39_words.txt', 'r') as file:
    BIP39_WORDS = set(word.strip() for word in file)

# Initialize the Slack client
slack_client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))

# Initialize the Slack Signature Verifier
signature_verifier = SignatureVerifier(os.getenv("SLACK_SIGNING_SECRET"))

# Initialize bot user_id
bot_id = slack_client.auth_test()['user_id'] 

# Track event IDs to ignore duplicates
processed_event_ids = set()

class SlackEvent(BaseModel):
    type: str
    user: str
    text: str
    channel: str

def react_description(query, user_id): 
    headers = {"Authorization": f"Bearer {os.getenv('BACKEND_API_KEY')}"}
    response = requests.post('https://knowlbot.aws.stg.ldg-tech.com/gpt', headers=headers, json={"user_input": query, "user_id": user_id}) # New
    formatted_output = response.json()['output']
    # Replace markdown link formatting with Slack link formatting
    link_pattern = r'\[(.*?)\]\((.*?)\)'
    formatted_output = re.sub(link_pattern, r'<\2|\1>', formatted_output)
    return formatted_output

@app.post("/")
async def slack_events(request: Request):
    # Get the request body
    body_bytes = await request.body()
    body = json.loads(body_bytes)

    # Verify the request from Slack
    if not signature_verifier.is_valid_request(body_bytes, request.headers):
        return Response(status_code=403)

    # Check if this is a URL verification challenge
    if body.get("type") == "url_verification":
        return {"challenge": body.get("challenge")}

    # Parse the event
    event = body.get('event')

    # Ignore duplicate events
    event_id = event.get('event_ts')
    if event_id in processed_event_ids:
        return Response(status_code=200)
    processed_event_ids.add(event_id)

    if event and (event.get('type') == "app_mention" or event.get('type') == "message"): #New
        # Check if the message event is from the bot itself
        if event.get('user') == bot_id:
            return Response(status_code=200)

        user_text = event.get('text')
        user_id = event.get('user')
        # Check for cryptocurrency addresses in the user's text
        if re.search(ETHEREUM_ADDRESS_PATTERN, user_text, re.IGNORECASE) or \
           re.search(BITCOIN_ADDRESS_PATTERN, user_text, re.IGNORECASE) or \
           re.search(LITECOIN_ADDRESS_PATTERN, user_text, re.IGNORECASE) or \
           re.search(DOGECOIN_ADDRESS_PATTERN, user_text, re.IGNORECASE) or \
           re.search(XRP_ADDRESS_PATTERN, user_text, re.IGNORECASE):
            response_text = "I'm sorry, but I can't assist with questions that include cryptocurrency addresses. Please remove the address and ask again."
        elif contains_bip39_phrase(user_text):
            response_text = "It looks like you've included a recovery phrase in your message. Please never share your recovery phrase. It is the master key to your wallet and should be kept private."
        else:
            # Event handler
            response_text = react_description(user_text, user_id)
        response_text = f'<@{user_id}> {response_text}'

        # Send a response back to Slack in the thread where the bot was mentioned
        slack_client.chat_postMessage(
            channel=event.get('channel'),
            text=response_text, 
            thread_ts=event.get('thread_ts') if event.get('thread_ts') else event.get('ts') 
 
        )

    return Response(status_code=200)
