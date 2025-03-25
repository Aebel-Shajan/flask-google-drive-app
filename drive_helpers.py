import io
from typing import Optional
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload


def retrieve_user_files(credentials: Credentials, parent_id:Optional[str] =None)-> list[dict]:
    # https://developers.google.com/drive/api/reference/rest/v3/files#File
    drive_service = build("drive", "v3", credentials=credentials)
    
    query = "mimeType != 'application/vnd.google-apps.folder' and trashed = false"
    if parent_id:
        query += f" and ('{parent_id}' in parents)"
    
    results = (
        drive_service
        .files()
        .list(
            q=query,
            fields="files(id, name, webViewLink)",
            orderBy="createdTime",
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


def upload_file(credentials: Credentials, file_path: str, file_metadata: dict):
    drive_service = build("drive", "v3", credentials=credentials)
    media = MediaFileUpload(file_path, resumable=True)
    file = (
        drive_service
        .files()
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


def get_or_create_nested_folder(credentials: Credentials, folder_path:str):
    service = build("drive", "v3", credentials=credentials)
    folder_names = folder_path.strip("/").split("/")
    parent_id = None

    for folder_name in folder_names:
        # Build the query
        query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        if parent_id:
            query += f" and '{parent_id}' in parents"

        # Search for the folder
        results = service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)',
            pageSize=1
        ).execute()
        items = results.get('files', [])

        if items:
            # Folder exists
            parent_id = items[0]['id']
        else:
            # Create the folder
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_id] if parent_id else []
            }
            folder = service.files().create(body=file_metadata, fields='id').execute()
            parent_id = folder['id']

    return parent_id



def file_exists(credentials: Credentials, name, parent_id):
    service = build("drive", "v3", credentials=credentials)
    query = f"name = '{name}' and '{parent_id}' in parents and trashed = false"
    results = service.files().list(
        q=query,
        spaces='drive',
        fields="files(id, name)",
    ).execute()

    files = results.get('files', [])
    return files


def upload_or_overwrite(credentials: Credentials, file_path, file_name, parent_id):
    print(credentials)
    
    service = build("drive", "v3", credentials=credentials)
    
    # Step 1: Check if file already exists
    existing_files = file_exists(credentials, file_name, parent_id)

    # Step 2: Prepare media and metadata
    media = MediaFileUpload(file_path, resumable=True) 
    file_metadata = {
        'name': file_name,
        'parents': [parent_id]
    }

    if len(existing_files) > 0:
        # Step 3A: Overwrite existing file
        file_id = existing_files[0]['id']
        updated = (
            service
            .files()
            .update(
                fileId=file_id,
                media_body=media,
            )
            .execute()
        )
        print(f"✅ Overwritten file ID: {updated['id']}")
        return updated['id']
    else:
        # Step 3B: Upload new file
        uploaded = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        print(f"🆕 Uploaded new file ID: {uploaded['id']}")
        return uploaded['id']