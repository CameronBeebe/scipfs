import click
import logging
from pathlib import Path
from .ipfs import IPFSClient
from .library import Library
import sys # Import sys for exit
from . import config as scipfs_config # Import the new config module

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default configuration directory
CONFIG_DIR = Path.home() / ".scipfs"

@click.group()
def cli():
    """SciPFS: Manage decentralized file libraries on IPFS.

    A command-line tool to create, join, and manage shared file libraries
    using the InterPlanetary File System (IPFS). Ensure your IPFS daemon
    is running before using SciPFS commands that interact with the network.
    """
    pass

@cli.command()
def init():
    """Initialize the SciPFS configuration directory.

    This command creates the necessary configuration directory (~/.scipfs)
    if it doesn't already exist. This directory stores local manifest files
    for the libraries you manage.

    Examples:
      scipfs init
    """
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        click.echo(f"Initialized SciPFS configuration at {CONFIG_DIR}")
    except OSError as e:
        click.echo(f"Error initializing configuration directory: {e}", err=True)
        sys.exit(1) # Use sys.exit for cleaner exit codes

@cli.command()
@click.argument("name")
def create(name: str):
    """Create a new library and its IPNS entry.

    Initializes a new library, generates an IPNS key named after the library,
    creates its first manifest, adds it to IPFS, pins it, and publishes it
    to the generated IPNS name. The IPNS name is the primary identifier
    to share for others to join and follow the library.

    Arguments:
      NAME: The desired unique name for the new library. This will also be
            used as the IPNS key name.

    Examples:
      scipfs create my-research-papers
    """
    try:
        ipfs_client = IPFSClient()
        library = Library(name, CONFIG_DIR, ipfs_client)
        library.create() # Generates key, saves manifest, publishes to IPNS
        
        if library.ipns_name and library.manifest_cid:
            click.echo(f"Successfully created library '{name}'.")
            click.echo(f"IPNS Name (share this with others): {library.ipns_name}")
            click.echo(f"Initial Manifest CID: {library.manifest_cid}")
            click.echo(f"Your local IPFS node is now publishing this library at the IPNS name.")
            click.echo(f"Note: IPNS propagation can take some time.")
        else:
            click.echo(f"Created library '{name}', but failed to get IPNS name or manifest CID.", err=True)
            sys.exit(1)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        click.echo(f"Hint: A library or IPNS key with the name '{name}' might already exist. Check local manifests or 'ipfs key list'.", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"An unexpected error occurred during 'create': {e}", err=True)
        sys.exit(1)

@cli.command()
@click.argument("ipns_name")
def join(ipns_name: str):
    """Join an existing library using its IPNS name.

    Resolves the IPNS name to get the latest manifest CID for the library,
    downloads the manifest from IPFS, and saves it locally. This allows you
    to access and follow a library shared via IPNS.

    Arguments:
      IPNS_NAME: The IPNS name of the library (e.g., /ipns/k51q...).

    Examples:
      scipfs join /ipns/k51q... (use the actual IPNS name)
    """
    try:
        if not ipns_name.startswith("/ipns/"):
            click.echo("Error: Invalid IPNS name. It should start with '/ipns/'.", err=True)
            sys.exit(1)

        ipfs_client = IPFSClient()
        # A temporary name is used; library.join() will update it from the fetched manifest.
        # The actual library name for the manifest file will be derived from the manifest content.
        temp_lib_instance = Library("temp_join_placeholder", CONFIG_DIR, ipfs_client)
        temp_lib_instance.join(ipns_name) 
        
        click.echo(f"Successfully joined library '{temp_lib_instance.name}' using IPNS name: {ipns_name}")
        click.echo(f"Manifest (CID: {temp_lib_instance.manifest_cid}) saved to {temp_lib_instance.manifest_path}")
        click.echo(f"Use 'scipfs list {temp_lib_instance.name}' to see files or 'scipfs update {temp_lib_instance.name}' to refresh.")
    except FileNotFoundError as e: # Specifically for IPNS resolution failure
        click.echo(f"Error joining library: Could not resolve IPNS name '{ipns_name}'. It might not exist or propagate yet.", err=True)
        sys.exit(1)
    except ValueError as e: # For other validation errors from library.join
        click.echo(f"Error joining library: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"An unexpected error occurred during 'join': {e}", err=True)
        sys.exit(1)

@cli.command()
@click.argument("name")
@click.argument("file_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def add(name: str, file_path: Path):
    """Add a file to the specified library.

    Uploads the file to IPFS, pins it, and updates the library's manifest.
    If you are the owner (creator) of this library (i.e., your IPFS node
    holds the IPNS key for it), the updated manifest will be published to the
    library's IPNS name. Otherwise, a new manifest CID will be generated,
    which you might need to share with the library owner.
    Requires username to be configured: 'scipfs config set username <username>'.

    Arguments:
      NAME: The name of the library.
      FILE_PATH: Path to the local file to add.

    Examples:
      scipfs add my-research-papers ./papers/paper1.pdf
    """
    try:
        username = scipfs_config.get_username()
        if not username:
            click.echo("Error: Username not set. Use 'scipfs config set username <your_username>' first.", err=True)
            sys.exit(1)

        ipfs_client = IPFSClient()
        library = Library(name, CONFIG_DIR, ipfs_client)
        
        if not library.manifest_path.exists():
             click.echo(f"Error: Local manifest for library '{name}' not found at {library.manifest_path}.", err=True)
             click.echo(f"Hint: Did you 'create' or 'join' the library '{name}' first?", err=True)
             sys.exit(1)
        
        original_manifest_cid = library.manifest_cid
        library.add_file(file_path, username) # This calls _save_manifest, which handles IPNS publish
        
        click.echo(f"Added '{file_path.name}' to library '{name}' (added by: {username}).")
        
        if library.manifest_cid != original_manifest_cid:
            click.echo(f"New Manifest CID: {library.manifest_cid}")
            if library.ipns_key_name == name and library.ipns_name: # Check if this instance is the publisher
                click.echo(f"The library's IPNS record ({library.ipns_name}) has been updated to point to this new manifest.")
                click.echo("Note: IPNS propagation can take some time for others to see the update.")
            else:
                click.echo("Your local manifest is updated. If this is a shared library you don't own,")
                click.echo("you may need to inform the library owner of this new manifest CID if you wish for it to be published.")
        elif library.manifest_cid == original_manifest_cid:
             click.echo("Warning: Manifest CID did not change. This might happen if the file content was identical or already listed.", err=True)
        else:
             click.echo("Warning: Could not retrieve the new manifest CID. Check logs.", err=True)

    except FileNotFoundError as e: # For the input file_path
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ValueError as e: # From library logic, e.g. loading issues.
         click.echo(f"Error processing library '{name}': {e}", err=True)
         sys.exit(1)
    except Exception as e:
        click.echo(f"An unexpected error occurred during 'add': {e}", err=True)
        sys.exit(1)

@cli.command(name="list")
@click.argument("name")
def list_cmd(name: str):
    """List all files in the specified library.

    Loads the local manifest for the given library name and displays
    the details (name, CID, size) of all files currently listed in it.

    Arguments:
      NAME: The name of the library whose files you want to list.

    Examples:
      scipfs list my-research-papers
    """
    try:
        ipfs_client = IPFSClient()
        library = Library(name, CONFIG_DIR, ipfs_client)
        if not library.manifest_path.exists():
             click.echo(f"Error: Local manifest for library '{name}' not found at {library.manifest_path}.", err=True)
             click.echo(f"Hint: Did you create or join the library '{name}' first?", err=True)
             sys.exit(1)

        files = library.list_files()
        if not files:
            click.echo(f"Library '{name}' is empty.")
        else:
            click.echo(f"Files in library '{name}':")
            # Consider adding table formatting later if needed
            for file_info in files:
                click.echo(f"- {file_info['name']} (CID: {file_info['cid']}, Size: {file_info.get('size', 'N/A')} bytes)")
    except Exception as e:
        click.echo(f"Error listing files for library '{name}': {e}", err=True)
        sys.exit(1)

@cli.command()
@click.argument("name")
@click.argument("file_name")
@click.argument("output_path", type=click.Path(path_type=Path))
def get(name: str, file_name: str, output_path: Path):
    """Download a file from the specified library.

    Retrieves the file's CID from the local library manifest, then downloads
    it from IPFS. Does not automatically pin the file.

    Arguments:
      NAME: The name of the library.
      FILE_NAME: The name of the file to download.
      OUTPUT_PATH: Local path to save the file. If a directory, saves with original name.

    Examples:
      scipfs get my-research-papers paper1.pdf ./downloads/
    """
    try:
        ipfs_client = IPFSClient()
        library = Library(name, CONFIG_DIR, ipfs_client)
        if not library.manifest_path.exists():
             click.echo(f"Error: Local manifest for library '{name}' not found at {library.manifest_path}.", err=True)
             click.echo(f"Hint: Did you create or join the library '{name}' first?", err=True)
             sys.exit(1)

        # Determine final output path (handle directory case)
        final_output_path = output_path
        if output_path.is_dir():
            final_output_path = output_path / file_name

        # Check if file already exists before attempting download? Optional.
        if final_output_path.exists():
             click.echo(f"Warning: Output file already exists: {final_output_path}", err=True)
             # Maybe add a --force option later? For now, we'll overwrite.

        click.echo(f"Attempting to download '{file_name}' from library '{name}' to {final_output_path}...")
        library.get_file(file_name, final_output_path)
        click.echo(f"Successfully downloaded '{file_name}' to {final_output_path}")

    except KeyError: # Raised by library.get_file if file_name not in manifest
        click.echo(f"Error: File '{file_name}' not found in the manifest for library '{name}'.", err=True)
        click.echo(f"Hint: Use 'scipfs list {name}' to see available files.", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error downloading file: {e}", err=True)
        sys.exit(1)

@cli.command(name="list-local")
def list_local():
    """List locally configured SciPFS libraries.

    Scans ~/.scipfs for manifest files and lists their names.
    """
    if not CONFIG_DIR.exists() or not CONFIG_DIR.is_dir():
        click.echo(f"Configuration directory {CONFIG_DIR} not found.", err=True)
        click.echo("Run 'scipfs init' first.", err=True)
        sys.exit(1)

    # Use a generator directly instead of converting to list immediately
    manifest_files_generator = CONFIG_DIR.glob("*_manifest.json")
    
    # Check if the generator yields any items
    try:
        first_file = next(manifest_files_generator)
    except StopIteration:
        click.echo("No local libraries found.")
        return
    
    # If we got here, there's at least one file.
    # We need to process the first file and then the rest of the generator.
    click.echo("Locally configured libraries:")
    
    # Process the first file we already fetched
    library_name_from_file = first_file.name.replace("_manifest.json", "")
    
    # Attempt to load manifest to get the actual name and IPNS if available
    try:
        ipfs_client = IPFSClient() # Needed for Library instantiation
        lib_instance = Library(library_name_from_file, CONFIG_DIR, ipfs_client)
        display_name = lib_instance.name # Name from manifest content
        ipns_info = f" (IPNS: {lib_instance.ipns_name})" if lib_instance.ipns_name else ""
        click.echo(f"- {display_name}{ipns_info}")
    except Exception: # Fallback if manifest is broken or lib can't load
        click.echo(f"- {library_name_from_file} (could not load details)")

    # Process the rest of the generator
    for manifest_path in manifest_files_generator:
        library_name_from_file = manifest_path.name.replace("_manifest.json", "")
        try:
            ipfs_client = IPFSClient()
            lib_instance = Library(library_name_from_file, CONFIG_DIR, ipfs_client)
            display_name = lib_instance.name
            ipns_info = f" (IPNS: {lib_instance.ipns_name})" if lib_instance.ipns_name else ""
            click.echo(f"- {display_name}{ipns_info}")
        except Exception:
            click.echo(f"- {library_name_from_file} (could not load details)")

@cli.command()
@click.argument("name")
def update(name: str):
    """Update a joined library from its IPNS name.

    Fetches the latest manifest CID published to the library's known IPNS name.
    If it's different from the local manifest CID, the new manifest is
    downloaded and saved, effectively updating your local view of the library.
    This command is for libraries you have 'join'ed.

    Arguments:
      NAME: The name of the locally configured library to update.
    """
    try:
        ipfs_client = IPFSClient()
        library = Library(name, CONFIG_DIR, ipfs_client)

        if not library.manifest_path.exists():
            click.echo(f"Error: Library '{name}' not found locally.", err=True)
            sys.exit(1)
        
        if not library.ipns_name:
            click.echo(f"Error: Library '{name}' does not have an IPNS name associated with it locally.", err=True)
            click.echo("This command is for libraries joined via IPNS. It might be a library you created, which updates automatically on 'add'.")
            sys.exit(1)

        click.echo(f"Checking for updates for library '{name}' from IPNS name: {library.ipns_name}...")
        current_local_cid = library.manifest_cid
        
        # We re-use the join logic for updating.
        # Create a temporary instance to perform the "join" which resolves and fetches.
        # The existing library instance (`library`) holds the old state for comparison.
        update_fetcher = Library(f"temp_update_{name}", CONFIG_DIR, ipfs_client) # Use a distinct temp name
        update_fetcher.join(library.ipns_name) # This resolves, fetches, and saves if different

        # After join, update_fetcher.manifest_cid will be the new CID from IPNS.
        # And update_fetcher.name will be the name from the fetched manifest (should match `name`).
        # The local file for `library.name` has been overwritten by update_fetcher.join's _save_manifest.

        if update_fetcher.manifest_cid == current_local_cid:
            click.echo(f"Library '{name}' is already up-to-date. Local CID: {current_local_cid}")
        else:
            click.echo(f"Library '{name}' updated.")
            click.echo(f"Old Manifest CID: {current_local_cid}")
            click.echo(f"New Manifest CID: {update_fetcher.manifest_cid}")
            click.echo(f"Manifest saved to {update_fetcher.manifest_path}") # Should be same as library.manifest_path

    except FileNotFoundError: # From library.join if IPNS name can't be resolved
        click.echo(f"Error updating library '{name}': Could not resolve its IPNS name {library.ipns_name}.", err=True)
        sys.exit(1)
    except ValueError as e: # From library logic
         click.echo(f"Error updating library '{name}': {e}", err=True)
         sys.exit(1)
    except Exception as e:
        click.echo(f"An unexpected error occurred during 'update {name}': {e}", err=True)
        sys.exit(1)

@cli.command()
@click.argument("name")
def info(name: str):
    """Display information about a local library.

    Shows details such as the library's name from the manifest, its IPNS name
    (if available), the current local manifest CID, and the number of files.

    Arguments:
      NAME: The name of the locally configured library.
    """
    try:
        ipfs_client = IPFSClient()
        library = Library(name, CONFIG_DIR, ipfs_client)

        if not library.manifest_path.exists():
            click.echo(f"Error: Library '{name}' not found locally at {library.manifest_path}", err=True)
            sys.exit(1)
        
        click.echo(f"Information for library: {library.name}") # Name from manifest
        click.echo(f"  Manifest File: {library.manifest_path}")
        if library.ipns_name:
            click.echo(f"  IPNS Name: {library.ipns_name}")
        else:
            click.echo("  IPNS Name: Not set (this might be a library created with an older version or joined by CID directly).")
        
        if library.ipns_key_name: # Only relevant if this node is the publisher
             click.echo(f"  IPNS Key Name (local): {library.ipns_key_name}")

        click.echo(f"  Current Manifest CID: {library.manifest_cid if library.manifest_cid else 'N/A (manifest not yet on IPFS or error)'}")
        
        num_files = len(library.manifest.get("files", {}))
        click.echo(f"  Number of files: {num_files}")

    except Exception as e:
        click.echo(f"An unexpected error occurred during 'info {name}': {e}", err=True)
        sys.exit(1)

# --- Configuration Commands ---
@cli.group()
def config():
    """Manage SciPFS configuration."""
    pass

@config.group("set")
def config_set():
    """Set configuration values."""
    pass

@config_set.command("username")
@click.argument("username")
def set_username_cmd(username: str):
    """Set the username to be associated with file additions."""
    try:
        # Basic validation (optional, can be expanded)
        if not username or len(username) < 3:
             click.echo("Error: Username must be at least 3 characters long.", err=True)
             sys.exit(1)
        
        scipfs_config.set_username(username)
        click.echo(f"Username set to: {username}")
    except Exception as e:
        click.echo(f"Error setting username: {e}", err=True)
        sys.exit(1)

# Ensure the main guard is present if this script is run directly
if __name__ == '__main__':
    cli()
