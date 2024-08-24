import os
import jieba
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageSendMessage
from rapidfuzz import process, fuzz

# Directory where the mime photos are stored
PHOTO_DIR = "./mimes/"

app = Flask(__name__)

# Load the Line API credentials from environment variables
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_input = event.message.text.lower()
    closest_photos = find_closest_mime_photos(user_input)

    if closest_photos:
        image_messages = [
            ImageSendMessage(original_content_url=photo[0], preview_image_url=photo[0])
            for photo in closest_photos
        ]
        line_bot_api.reply_message(event.reply_token, image_messages)
    else:
        line_bot_api.reply_message(event.reply_token, TextMessage(text="Sorry, no matching mime found."))


def load_mime_photos(directory):
    """
    Recursively load mime photo file paths and their associated keywords.
    """
    mime_photos = {}
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(('.png', '.jpg', '.jpeg')):
                file_path = os.path.join(root, file)
                photo_name = os.path.splitext(file)[0]  # Extract the filename without the extension
                mime_photos[photo_name] = file_path
    return mime_photos

def segment_text(text):
    """
    Segment the input text using Jieba for Chinese text segmentation.
    """
    return " ".join(jieba.cut(text))

def find_closest_mime_photos(user_input, top_n=3):
    """
    Find the mime photo that most closely matches the user input.
    """
    # Load mime photos from the directory (you may want to cache this for performance)
    mime_photos = load_mime_photos(PHOTO_DIR)
    
    # Segment the user input to handle Chinese semantics
    segmented_input = segment_text(user_input)

    # Get the top N matches
    matches = process.extract(segmented_input, mime_photos.keys(), scorer=fuzz.partial_ratio, limit=top_n)

    # Filter matches by a threshold score (optional)
    threshold_score = 50
    closest_photos = [(mime_photos[match[0]], match[1]) for match in matches if match[1] > threshold_score]
    
    return closest_photos

if __name__ == "__main__":
    app.run(debug=True)
