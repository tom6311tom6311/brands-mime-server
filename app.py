import os
import jieba
import tempfile
import random
import shutil
import urllib.parse
from flask import Flask, request, abort, send_from_directory
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, ImageSendMessage, TextSendMessage
from rapidfuzz import process, fuzz

# Directory where the mime photos are stored
PHOTO_DIR = "mimes"
UPLOADED_PHOTO_DIR = "mimes/uploaded"

app = Flask(__name__)

# Load the Line API credentials from environment variables
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))
base_url = os.getenv('BASE_URL')

# Temp storage to track which user is uploading a photo
user_uploads = {}

@app.route('/images/<path:filename>')
def serve_image(filename):
    return send_from_directory(PHOTO_DIR, filename)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    print("Request body: " + body)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    # Download the image
    message_id = event.message.id
    message_content = line_bot_api.get_message_content(message_id)

    # Save the image to a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
        for chunk in message_content.iter_content():
            tmp_file.write(chunk)
        tmp_file_path = tmp_file.name

    # Store the temporary file path associated with the user's ID
    user_id = event.source.user_id
    user_uploads[user_id] = tmp_file_path

    # Prompt the user to provide a title or keywords
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="請為這張圖片提供一個15字內的標題或關鍵詞:")
    )

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_input = event.message.text.lower()
    user_id = event.source.user_id

    print(f"User {user_id} input: {user_input}")

    # Check if the user is in the process of uploading a mime
    if user_id in user_uploads:
        # The user provided a title for the uploaded image
        tmp_file_path = user_uploads.pop(user_id)
        save_mime_photo(tmp_file_path, user_input)

        # Notify the user that the photo has been saved
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"已經儲存圖片")
        )
    else:
        closest_photos = find_closest_mime_photos(user_input)
        if closest_photos:
            image_messages = [
                ImageSendMessage(
                    original_content_url=f"{base_url}/images/{urllib.parse.quote(photo[0])}",
                    preview_image_url=f"{base_url}/images/{urllib.parse.quote(photo[0])}"
                )
                for photo in closest_photos
            ]
            line_bot_api.reply_message(event.reply_token, image_messages)
        else:
            line_bot_api.reply_message(event.reply_token, TextMessage(text="抱歉，找不到相關的圖..."))

def save_mime_photo(tmp_file_path, title):
    """
    Save the uploaded mime photo with the provided title.
    """
    save_path = os.path.join(UPLOADED_PHOTO_DIR, f"{title}.jpg")
    shutil.move(tmp_file_path, save_path)

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
                mime_photos[photo_name] = file_path[len(directory)+1:] # Exclude `directory/` from the path
    return mime_photos

def segment_text(text):
    """
    Segment the input text using Jieba for Chinese text segmentation.
    """
    return " ".join(jieba.cut(text))

def find_closest_mime_photos(user_input, top_n=3):
    """
    Find the closest mime photo and randomly select (top_n - 1) photos from 
    the next 2*(top_n - 1) closest matches, excluding the closest one.
    """
    # Load mime photos from the directory (you may want to cache this for performance)
    mime_photos = load_mime_photos(PHOTO_DIR)
    
    # Segment the user input to handle Chinese semantics
    segmented_input = segment_text(user_input)

    # Get the top 2N matches
    matches = process.extract(segmented_input, mime_photos.keys(), scorer=fuzz.partial_ratio, limit=2*top_n)

    if not matches:
        return []
    
    # The first match is the closest one
    closest_photo = matches[0]

     # The remaining matches are used to randomly select (top_n - 1) photos
    remaining_matches = matches[1:]

    # Randomly select (top_n - 1) photos from the remaining matches
    selected_photos = random.sample(remaining_matches, min(len(remaining_matches), top_n - 1))

    closest_photos = [(mime_photos[closest_photo[0]], closest_photo[1])] + [
        (mime_photos[match[0]], match[1]) for match in selected_photos
    ]

    return closest_photos

if __name__ == "__main__":
    app.run(debug=True)
