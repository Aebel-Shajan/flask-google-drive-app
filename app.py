import io
import os
from typing import TypedDict
import flask
from flask import Flask, request, redirect, url_for, render_template, flash, session
from werkzeug.utils import secure_filename
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
import yd_extractor

import drive_helpers as drive_helpers
import yd_extractor.strong

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



class DriveFileInfo(TypedDict):
    webViewLink: str
    id: str
    name: str

# Routes
@app.route("/")
def index():
    if "credentials" not in session:
        return render_template("index.html", logged_in=False)

    # Get user info
    credentials = Credentials(**session["credentials"])
    user_info = drive_helpers.retrieve_user_info(credentials)

    # Get the list of user's files
    input_folder_id = drive_helpers.get_or_create_nested_folder(credentials, "year-in-data/inputs")
    files: list[DriveFileInfo] = drive_helpers.retrieve_user_files(credentials, parent_id=input_folder_id)
    print(files)
    data_sources = []
    strong_source_found = False
    for file in files:
        if file["name"].startswith("strong") and not strong_source_found:
            data_sources.append(
                {
                    "source": "Strong",
                    **file
                }
            )
    
    return render_template(
        "index.html", logged_in=True, user_info=user_info, data_sources=data_sources
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
        credentials = Credentials(**session["credentials"])
        
        # Check if the post request has the file part
        if "file" not in request.files:
            flash("No file part", "danger")
            return redirect(request.url)
        file = request.files["file"]
        
        input_folder_id = drive_helpers.get_or_create_nested_folder(
            credentials,
            "year-in-data/inputs"
        )

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
            drive_helpers.upload_file(
                credentials, 
                file_path,     
                file_metadata = {"name": filename, "parents": [input_folder_id]}
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
    file_io = drive_helpers.download_file(credentials, file_id)
    file_name = drive_helpers.get_file_name(credentials, file_id)

    # Create a Flask response with the file
    response = flask.make_response(file_io.read())
    response.headers["Content-Disposition"] = f'attachment; filename="{file_name}"'
    return response

@app.route("/process")
def process_file():
    if "credentials" not in session:
        flash("You need to login first", "warning")
        return redirect(url_for("index"))
    file_id = request.args.get('file_id')
    source = request.args.get('source')
    
    credentials = Credentials(**session["credentials"])
    file_io = drive_helpers.download_file(credentials, file_id)

    if source.lower() == "strong":
        df = yd_extractor.strong.process_workouts(io.TextIOWrapper(file_io))
        save_path = app.config["UPLOAD_FOLDER"] + "/strong.csv"
        df.to_csv(save_path, index=False)
        output_folder_id = drive_helpers.get_or_create_nested_folder(
            credentials, 
            "year-in-data/outputs"
        )
        drive_helpers.upload_or_overwrite(
            credentials=credentials, 
            file_path=save_path, 
            file_name="strong.csv",
            parent_id=output_folder_id
        )
        os.remove(save_path)

    return "yo"


if __name__ == "__main__":
    app.run(debug=True)
