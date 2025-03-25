import io
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload


def retrieve_user_files(credentials: Credentials)-> list[dict]:
    # https://developers.google.com/drive/api/reference/rest/v3/files#File
    drive_service = build("drive", "v3", credentials=credentials)
    results = (
        drive_service.files()
        .list(
            fields="files(id, name, webViewLink)",
            pageSize=10,
        )
        .execute()
    )
    files = results.get("files", [])
    return files

def retrieve_user_info(credentials: Credentials):
    service = build("oauth2", "v2", credentials=credentials)
    user_info = service.userinfo().get().execute()
    return user_info


def upload_file(credentials: Credentials, filename: str, file_path: str):
                
    drive_service = build("drive", "v3", credentials=credentials)

    file_metadata = {"name": filename}
    media = MediaFileUpload(file_path, resumable=True)

    file = (
        drive_service.files()
        .create(body=file_metadata, media_body=media, fields="id")
        .execute()
    )
    
    
def download_file(credentials: Credentials, file_id:str):
    drive_service = build("drive", "v3", credentials=credentials)
    # Download file
    request = drive_service.files().get_media(fileId=file_id)
    file_io = io.BytesIO()
    downloader = MediaIoBaseDownload(file_io, request)
    
    done = False
    while done is False:
        status, done = downloader.next_chunk()

    file_io.seek(0)
    
    return file_io

def get_file_name(credentials: Credentials, file_id: str):
    # Get file metadata first to get the name
    drive_service = build("drive", "v3", credentials=credentials)
    file_metadata = drive_service.files().get(fileId=file_id).execute()
    filename = file_metadata["name"]
    return filename