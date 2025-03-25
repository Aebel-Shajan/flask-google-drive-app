import os
import flask
from flask import Flask, request, redirect, url_for, render_template, flash, session
from werkzeug.utils import secure_filename
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials

import drive_helpers as drive_helpers

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
    user_info = drive_helpers.retrieve_user_info(credentials)

    # Get the list of user's images
    files = drive_helpers.retrieve_user_files(credentials)

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

    options = [
        "kindle",
        "fitbit",
        "strong"
    ]

    if request.method == "POST":
        selected_data_source = request.form.get('data-source')
        
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
            drive_helpers.upload_file(credentials, filename, file_path)

            # Clean up temporary file
            os.remove(file_path)

            flash(f"File {filename} successfully uploaded to Google Drive!", "success")
            return redirect(url_for("index"))
    
    return render_template("upload.html", options=options)


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


if __name__ == "__main__":
    app.run(debug=True)
