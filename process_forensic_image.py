# process_forensic_image.py
import os
from typing import List

import requests
from rich.console import Console
from src.config import settings

console = Console()

# --- Configuration ---
# The path where the Windows 11 drive image (C:) is mounted ON STARLORD
DRIVE_MOUNT_POINT = "/mnt/forensic_image/C/"
API_ENDPOINT = "http://192.168.68.55:8002/ingest_folder"
TARGET_COLLECTION = settings.QDRANT_COLLECTION
REQUEST_TIMEOUT = 1800  # 30 minutes for massive directory scans


def get_critical_paths(username: str) -> List[str]:
    """Generates the critical hidden paths based on the forensic analysis document."""
    user_profile = f"Users/{username}"
    appdata_local = f"{user_profile}/AppData/Local"
    appdata_roaming = f"{user_profile}/AppData/Roaming"

    paths = [
        # Office (Ref: Sections 2.1, 2.2, 2.3.1, 2.4, 6.1)
        f"{appdata_local}/Microsoft/Office/16.0/OfficeFileCache",  # Critical: Document Cache
        f"{appdata_local}/Microsoft/Office/16.0/Wef",  # Add-in Cache
        f"{appdata_local}/Microsoft/FontCache/4/CloudFonts",  # Cloud Fonts
        f"{appdata_local}/Microsoft/Office/Licenses",  # Licensing Tokens
        f"{appdata_roaming}/Microsoft/Word",  # AutoRecover
        f"{appdata_local}/Microsoft/Office/UnsavedFiles",
        # Outlook (Ref: Sections 3.1, 3.2, 3.3)
        f"{appdata_local}/Microsoft/Olk",  # New Outlook Data
        f"{appdata_local}/Microsoft/Outlook",  # Classic (OST/PST/RoamCache)
        # Attachment Cache (Content.Outlook). Target parent as subfolder is randomized.
        f"{appdata_local}/Microsoft/Windows/INetCache/Content.Outlook",
        # Teams (Ref: Sections 4.1, 4.2)
        f"{appdata_roaming}/Microsoft/Teams",  # Classic Teams
        # OneDrive (Ref: Section 5.2)
        f"{appdata_local}/Microsoft/OneDrive/logs",  # Sync Logs & Obfuscation Map
        # Web Browsers & UWP Packages (Critical for databases/caches)
        f"{appdata_local}/Google/Chrome/User Data",
        f"{appdata_local}/Microsoft/Edge/User Data",
        # Includes New Teams, WebViewHost, etc.
        f"{appdata_local}/Packages",
    ]
    return paths


def trigger_ingestion(remote_path: str):
    """Sends the ingestion request to the API."""
    # The API expects the full path on the Starlord filesystem
    full_path_on_starlord = os.path.join(DRIVE_MOUNT_POINT, remote_path)

    console.print(
        f"[bold cyan]🔍 Triggering Ingestion for:[/bold cyan] {full_path_on_starlord}"
    )

    payload = {
        "remote_folder_path": full_path_on_starlord,
        "collection": TARGET_COLLECTION,
    }

    try:
        response = requests.post(API_ENDPOINT, json=payload, timeout=REQUEST_TIMEOUT)
        if response.status_code == 202:
            result = response.json()
            console.print(
                f"  [green]✅ Queued. Batch ID:[/green] {result['batch_id']}, Files: {result['total_files_queued']}"
            )
        elif response.status_code == 400:
            # API returns 400 if the path doesn't exist on Starlord's filesystem
            console.print(
                f"  [yellow]Skipping (Path likely does not exist on image):[/yellow] {remote_path}"
            )
        else:
            console.print(
                f"  [red]❌ Error![/red] Status: {response.status_code}, Details: {response.text}"
            )
    except requests.exceptions.RequestException as e:
        console.print(
            f"[bold red]CRITICAL ERROR: Connection failed or timed out.[/bold red] {e}"
        )


def main():
    # Strategy: We perform a comprehensive scan of the /Users directory.
    # This covers standard user files (Documents, Downloads, A/V) AND all critical hidden AppData locations analyzed in the document.

    # 1. Comprehensive User Data Scan
    console.print(
        "\n--- [bold yellow]Initiating Comprehensive Scan of /Users Directory[/bold yellow] ---"
    )
    console.print(
        "This captures standard files, A/V media, and all hidden forensic AppData locations."
    )
    trigger_ingestion("Users")

    # 2. Process System-Level Data (Ref: Section 6.2)
    console.print("\n--- [bold blue]Processing System-Level Data[/bold blue] ---")
    # ProgramData (Includes Telemetry at ProgramData/Microsoft/Diagnostics)
    trigger_ingestion("ProgramData")
    # Windows Logs and System Artifacts
    trigger_ingestion("Windows/Logs")
    trigger_ingestion("Windows/System32/config")  # Registry Hives

    console.print(
        "\n[bold green]Ingestion Orchestration Complete. Monitor the workers on Starlord (tmux attach -t forensic-ingestion) and Grafana.[/bold green]"
    )


if __name__ == "__main__":
    main()
    main()
