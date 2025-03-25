import os
import json
import flask
from flask import Flask, request, redirect, url_for, render_template, flash, session
from werkzeug.utils import secure_filename
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import io

# Configuration
app = Flask(__name__)
app.secret_key = os.urandom(24)  # In production, use a stable secret key
app.config["UPLOAD_FOLDER"] = "temp_uploads"
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max upload

# Allow OAuth over HTTP for local development
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

# Google OAuth configuration
# In a real application, store these in environment variables
CLIENT_SECRETS_FILE = "client_secret.json"  # Downloaded from Google Cloud Console
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]


# Helper functions
def credentials_to_dict(credentials):
    return {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
    }


def create_flow():
    return Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=url_for("oauth2callback", _external=True),
    )


# Routes
@app.route("/")
def index():
    if "credentials" not in session:
        return render_template("index.html", logged_in=False)

    # Get user info
    credentials = Credentials(**session["credentials"])
    service = build("oauth2", "v2", credentials=credentials)
    user_info = service.userinfo().get().execute()

    # Get the list of user's images
    drive_service = build("drive", "v3", credentials=credentials)
    results = (
        drive_service.files()
        .list(
            q="mimeType contains 'image/'",
            fields="files(id, name, webViewLink)",
            pageSize=10,
        )
        .execute()
    )
    files = results.get("files", [])

    return render_template(
        "index.html", logged_in=True, user_info=user_info, files=files
    )


@app.route("/login")
def login():
    flow = create_flow()
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",  # Force to get a refresh token
    )
    session["state"] = state
    return redirect(authorization_url)


@app.route("/oauth2callback")
def oauth2callback():
    state = session["state"]
    flow = create_flow()
    flow.fetch_token(authorization_response=request.url)

    credentials = flow.credentials
    session["credentials"] = credentials_to_dict(credentials)

    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    if "credentials" in session:
        del session["credentials"]
    return redirect(url_for("index"))


@app.route("/upload", methods=["GET", "POST"])
def upload_file():
    if "credentials" not in session:
        flash("You need to login first", "warning")
        return redirect(url_for("index"))

    if request.method == "POST":
        # Check if the post request has the file part
        if "file" not in request.files:
            flash("No file part", "danger")
            return redirect(request.url)

        file = request.files["file"]

        # If user does not select file, browser also
        # submit an empty part without filename
        if file.filename == "":
            flash("No selected file", "danger")
            return redirect(request.url)

        if file:
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(file_path)

            # Upload to Google Drive
            credentials = Credentials(**session["credentials"])
            drive_service = build("drive", "v3", credentials=credentials)

            file_metadata = {"name": filename}
            media = MediaFileUpload(file_path, resumable=True)

            file = (
                drive_service.files()
                .create(body=file_metadata, media_body=media, fields="id")
                .execute()
            )

            # Clean up temporary file
            os.remove(file_path)

            flash(f"File {filename} successfully uploaded to Google Drive!", "success")
            return redirect(url_for("index"))

    return render_template("upload.html")


@app.route("/download/<file_id>")
def download_file(file_id):
    if "credentials" not in session:
        flash("You need to login first", "warning")
        return redirect(url_for("index"))

    credentials = Credentials(**session["credentials"])
    drive_service = build("drive", "v3", credentials=credentials)

    # Get file metadata first to get the name
    file_metadata = drive_service.files().get(fileId=file_id).execute()
    filename = file_metadata["name"]

    # Download file
    request = drive_service.files().get_media(fileId=file_id)
    file_io = io.BytesIO()
    downloader = MediaIoBaseDownload(file_io, request)

    done = False
    while done is False:
        status, done = downloader.next_chunk()

    file_io.seek(0)

    # Create a Flask response with the file
    response = flask.make_response(file_io.read())
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


if __name__ == "__main__":
    app.run(debug=True)
