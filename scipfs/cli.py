import click
import logging
from pathlib import Path
from .ipfs import IPFSClient
from .library import Library
import sys # Import sys for exit
from . import config as scipfs_config # Import the new config module
from . import __version__ as scipfs_version # Import scipfs version
import os # Added for path operations
from typing import Set, Dict, List, Optional # Added Set, Dict, Optional
import subprocess
import json

# Configure logging
# Basic config for the whole application, individual loggers can be adjusted
# Set a default level that will be overridden if --verbose is used.
logging.basicConfig(stream=sys.stderr, level=logging.WARNING)

# Get loggers for scipfs modules
scipfs_logger = logging.getLogger("scipfs") # Root logger for the application
# Individual module loggers can also be grabbed if needed for finer control, but often setting the root is enough.
# For example:
# ipfs_module_logger = logging.getLogger("scipfs.ipfs")
# library_module_logger = logging.getLogger("scipfs.library")

# Default configuration directory
CONFIG_DIR = Path.home() / ".scipfs"

# Ensure CONFIG_DIR is created if it doesn't exist for library manifests
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
scipfs_config_instance = scipfs_config.SciPFSConfig(CONFIG_DIR)

# Shell completion for library file names
def complete_file_names(ctx, param, incomplete):
    """Provides autocompletion for file names within a specified library for the get command."""
    # ctx.params should contain the arguments parsed so far
    # For 'scipfs get <name> <file_name>', 'name' should be in ctx.params
    library_name = ctx.params.get('name')
    if not library_name:
        return []
    
    original_level = library_logger.level
    library_logger.setLevel(logging.ERROR) # Suppress INFO logs from library module
    
    try:
        # We don't need a full IPFS client connection just for listing files from manifest
        # Minimal library init to load manifest for listing files:
        # Temporarily suppress IPFSClient connection errors if any, for completion speed.
        class MinimalIPFSClient:
            def add_json(self, _):
                return "dummy_cid_for_completion"
            def get_json(self, _):
                return {}
            def pin(self, _):
                pass
            def unpin(self, _):
                pass
            def add_file(self, _):
                return "dummy_cid_for_completion"
            def get_file(self, _, __):
                pass
            def resolve_ipns_name(self, _):
                return "/ipfs/dummy_cid_for_completion"
            def publish_to_ipns(self, _, __):
                pass
            def generate_ipns_key(self, _):
                return {"Name": "dummy_key", "Id": "dummy_id_for_completion"}
            def list_ipns_keys(self):
                return []
            def remove_ipns_key(self, _):
                pass

        library = Library(library_name, CONFIG_DIR, MinimalIPFSClient()) 
        if library.manifest_path.exists():
            # list_files returns a list of dicts, each with a 'name' key
            return [
                file_info['name'] for file_info in library.list_files() 
                if file_info['name'].startswith(incomplete)
            ]
    except Exception:
        # Log to a debug file or stderr if needed, but don't break completion
        # For example: print(f"Completion error: {e}", file=sys.stderr)
        pass # Silently fail on error to avoid breaking completion
    finally:
        library_logger.setLevel(original_level) # Restore original logging level
    return []

@click.group()
@click.option("--verbose", "verbose_flag", is_flag=True, help="Enable INFO level logging for scipfs operations.")
@click.pass_context # Needed to access the verbose_flag in the group context
def cli(ctx, verbose_flag: bool):
    """SciPFS: Manage decentralized file libraries on IPFS.

    A command-line tool to create, join, and manage shared file libraries
    using the InterPlanetary File System (IPFS). Ensure your IPFS daemon
    is running before using SciPFS commands that interact with the network.
    """
    ctx.ensure_object(dict)
    ctx.obj['VERBOSE'] = verbose_flag
    if verbose_flag:
        scipfs_logger.setLevel(logging.INFO)
        # If you had individual loggers and wanted them all at INFO:
        # ipfs_module_logger.setLevel(logging.INFO)
        # library_module_logger.setLevel(logging.INFO)
        # logging.getLogger("scipfs.config").setLevel(logging.INFO)
        scipfs_logger.info("Verbose logging enabled.")
    else:
        # Explicitly set to WARNING if not verbose, to ensure it overrides any other potential default
        scipfs_logger.setLevel(logging.WARNING)

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
@click.pass_context # Pass context to access verbose flag if needed inside commands
def create(ctx, name: str):
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
    except ConnectionError as e:
        click.echo(f"Error connecting to IPFS: {e}", err=True)
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
        username = scipfs_config_instance.get_username()
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
@click.argument("file_name", required=False, shell_complete=complete_file_names)
@click.argument("output_path", type=click.Path(path_type=Path), required=False)
@click.option("--all", "all_files", is_flag=True, help="Download all files from the library.")
@click.option("--pin", "pin_file", is_flag=True, help="Pin the downloaded file(s) to the local IPFS node.")
def get(name: str, file_name: str, output_path: Path, all_files: bool, pin_file: bool):
    """Download file(s) from the specified library.

    If --all is specified, downloads all files in the library.
    The FILE_NAME argument is ignored if --all is used.
    If OUTPUT_PATH is provided with --all, it's used as the target directory.
    If OUTPUT_PATH is not provided with --all, files are downloaded into a
    new directory named after the library in the current working directory.

    When not using --all, FILE_NAME and OUTPUT_PATH are required to specify
    which file to download and where to save it.

    Use --pin to also pin the downloaded file(s) to your local IPFS node,
    helping to keep them available on the network.

    Arguments:
      NAME: The name of the library.
      FILE_NAME: The name of the file to download (ignored if --all is used).
      OUTPUT_PATH: Local path to save the file, or directory for --all.

    Examples:
      scipfs get my-library report.pdf ./downloads/report.pdf
      scipfs get my-library report.pdf ./downloads/report.pdf --pin
      scipfs get my-library --all ./downloaded_library_files/
      scipfs get my-library --all --pin
    """
    try:
        ipfs_client = IPFSClient()
        library = Library(name, CONFIG_DIR, ipfs_client)

        if not library.manifest_path.exists():
            click.echo(f"Error: Local manifest for library '{name}' not found at {library.manifest_path}.", err=True)
            click.echo(f"Hint: Did you 'create' or 'join' the library '{name}' first?", err=True)
            sys.exit(1)

        if all_files:
            # If --all is used, and file_name is given but output_path is not,
            # assume file_name was intended as the output_path.
            if file_name and output_path is None:
                try:
                    # Attempt to convert file_name to a Path object
                    # This also helps validate if it's a plausible path string
                    output_path = Path(file_name)
                    file_name = None # Clear file_name as it has been re-assigned
                except TypeError:
                    # file_name was not a valid path string, treat as an actual file_name
                    # and let the later logic warn if file_name is ignored.
                    pass # output_path remains None

            if file_name:
                click.echo(f"Warning: FILE_NAME ('{file_name}') is ignored when --all is used.", err=True)

            files_to_download = library.list_files()
            if not files_to_download:
                click.echo(f"No files found in library '{name}'.")
                return

            if output_path:
                target_dir = output_path
                # Ensure target_dir is a directory and exists
                if target_dir.exists() and not target_dir.is_dir():
                    click.echo(f"Error: Output path '{target_dir}' exists and is not a directory.", err=True)
                    sys.exit(1)
                target_dir.mkdir(parents=True, exist_ok=True)
            else:
                target_dir = Path.cwd() / name
                target_dir.mkdir(parents=True, exist_ok=True)
                click.echo(f"No output path specified. Files will be downloaded to ./{name}/")

            click.echo(f"About to download {len(files_to_download)} file(s) from library '{name}' to '{target_dir}'.")
            if pin_file:
                click.echo("Downloaded files will also be pinned to your local IPFS node.")
            if not click.confirm("Proceed?"):
                click.echo("Download cancelled.")
                return

            for file_info in files_to_download:
                f_name = file_info['name']
                f_cid = file_info.get('cid') # Get CID from file_info
                dest_path = target_dir / f_name
                try:
                    click.echo(f"Downloading '{f_name}' to '{dest_path}'...")
                    library.get_file(f_name, dest_path) # get_file uses file_name to lookup CID internally
                    click.echo(f"Successfully downloaded '{f_name}'.")
                    if pin_file:
                        if f_cid:
                            click.echo(f"Pinning '{f_name}' (CID: {f_cid})...")
                            ipfs_client.pin(f_cid)
                            click.echo(f"Successfully pinned '{f_name}'.")
                        else:
                            click.echo(f"Warning: Could not pin '{f_name}', CID not found in manifest details.", err=True)
                except FileNotFoundError:
                    click.echo(f"Error: File '{f_name}' not found in library manifest for download.", err=True)
                except Exception as e_file:
                    click.echo(f"Error downloading file '{f_name}': {e_file}", err=True)
            click.echo("Finished processing all files.")

        else: # Not --all, so download a single specified file
            if not file_name or not output_path:
                click.echo("Error: FILE_NAME and OUTPUT_PATH are required when not using --all.", err=True)
                click.echo("Usage: scipfs get <library_name> <file_name> <output_path>")
                click.echo("Or:    scipfs get <library_name> --all [output_directory]")
                sys.exit(1)
            
            # Determine final output path for single file download
            if output_path.is_dir():
                final_output_path = output_path / file_name
            else:
                final_output_path = output_path
            
            # Ensure the parent directory of the final output path exists
            final_output_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                # For single file, get its CID for potential pinning
                file_details = library.manifest.get("files", {}).get(file_name)
                file_cid = file_details.get("cid") if file_details else None

                click.echo(f"Downloading '{file_name}' from library '{name}' to '{final_output_path}'...")
                library.get_file(file_name, final_output_path)
                click.echo(f"Successfully downloaded '{file_name}' to '{final_output_path}'.")

                if pin_file:
                    if file_cid:
                        click.echo(f"Pinning '{file_name}' (CID: {file_cid})...")
                        ipfs_client.pin(file_cid)
                        click.echo(f"Successfully pinned '{file_name}'.")
                    else:
                        click.echo(f"Warning: Could not pin '{file_name}', CID not found in manifest.", err=True)

            except FileNotFoundError: # This can be from library.get_file if file not in manifest
                click.echo(f"Error: File '{file_name}' not found in library '{name}'. Check the manifest.", err=True)
                sys.exit(1)
            except Exception as e:
                click.echo(f"An unexpected error occurred during 'get': {e}", err=True)
                sys.exit(1)

    except FileNotFoundError as e: # Should primarily catch issue with library manifest itself
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ValueError as e: # From Library init if manifest is malformed for example
        click.echo(f"Error processing library '{name}': {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"An unexpected error occurred: {e}", err=True)
        sys.exit(1)

@cli.command(name="list-local")
def list_local_cmd():
    """List all local SciPFS libraries."""
    try:
        manifest_paths = list(CONFIG_DIR.glob("*_manifest.json"))
        if not manifest_paths:
            click.echo("No local SciPFS libraries found.")
            click.echo(f"(Configuration directory searched: {CONFIG_DIR.resolve()})")
            return

        click.echo("Local SciPFS Libraries:")
        for manifest_path in manifest_paths:
            library_name = manifest_path.name.replace("_manifest.json", "")
            # Potentially load library to get name from manifest if different
            try:
                # Minimal load just to get actual name and maybe basic info
                temp_ipfs_client = IPFSClient() # Create a temporary client instance
                lib = Library(library_name, CONFIG_DIR, temp_ipfs_client)
                click.echo(f"- {lib.name} (Found as: {library_name}_manifest.json)")
            except ConnectionError:
                 click.echo(f"- {library_name} (Manifest: {library_name}_manifest.json - Warning: Could not connect to IPFS to confirm library name)")
            except Exception as e_load:
                 click.echo(f"- {library_name} (Manifest: {library_name}_manifest.json - Warning: Could not fully load library: {e_load})")
                 
    except Exception as e:
        click.echo(f"An unexpected error occurred during 'list-local': {e}", err=True)
        sys.exit(1)

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
        
        scipfs_config_instance.set_username(username)
        click.echo(f"Username set to: {username}")
    except Exception as e:
        click.echo(f"Error setting username: {e}", err=True)
        sys.exit(1)

@cli.command(name="list-pinned")
def list_pinned_cmd():
    """List files from local SciPFS libraries that are pinned on the IPFS node.

    This command checks your local IPFS node for all pinned CIDs and then
    cross-references them with the files listed in your local SciPFS library
    manifests. It helps you see which of your library files are actively pinned.
    It will also list pinned CIDs that are not part of any known library files (e.g. manifests).
    """
    try:
        ipfs_client = IPFSClient()
        pinned_cids = ipfs_client.get_pinned_cids()

        if not pinned_cids:
            click.echo("No CIDs are currently pinned on your local IPFS node.")
            return

        click.echo(f"Found {len(pinned_cids)} pinned CIDs on your local IPFS node. Checking against local libraries...")
        
        found_library_files_pinned = False
        processed_cids = set() # To keep track of CIDs we've identified as library files

        if not CONFIG_DIR.exists() or not CONFIG_DIR.is_dir():
            click.echo(f"SciPFS configuration directory {CONFIG_DIR} not found. Cannot check library manifests.", err=True)
            # Still list non-library pinned CIDs later if any
        else:
            manifest_paths = list(CONFIG_DIR.glob("*_manifest.json"))
            if not manifest_paths:
                click.echo("No local SciPFS libraries found to check against pinned CIDs.")
            else:
                click.echo("\n--- Pinned SciPFS Library Files ---")
                for manifest_path in manifest_paths:
                    library_name_from_file = manifest_path.name.replace("_manifest.json", "")
                    try:
                        # Use a minimal IPFS client for library loading if full client not needed for this op
                        # However, IPFSClient() is already instantiated, so we can reuse it.
                        # The main IPFSClient will be used for Library init, which is fine.
                        library = Library(library_name_from_file, CONFIG_DIR, ipfs_client)
                        if not library.manifest_path.exists(): # Should not happen if globbed correctly
                            continue
                        
                        # Ensure library.name is loaded from manifest if different from file-derived name
                        actual_library_name = library.name 
                        
                        for file_info in library.list_files():
                            file_cid = file_info.get('cid')
                            if file_cid and file_cid in pinned_cids:
                                click.echo(f"  Library: {actual_library_name}")
                                click.echo(f"    File: {file_info['name']}")
                                click.echo(f"    CID: {file_cid}")
                                click.echo("    Status: Pinned")
                                click.echo("---")
                                found_library_files_pinned = True
                                processed_cids.add(file_cid)
                    except Exception as e_lib:
                        click.echo(f"Warning: Could not process library manifest {manifest_path.name}: {e_lib}", err=True)
            
        if not found_library_files_pinned and manifest_paths:
             click.echo("No files from your local SciPFS libraries appear to be pinned.")

        # Check for other pinned CIDs not identified as library files
        other_pinned_cids = pinned_cids - processed_cids
        if other_pinned_cids:
            click.echo("\n--- Other Pinned CIDs (e.g., manifests, non-library content) ---")
            for cid in sorted(list(other_pinned_cids)):
                click.echo(f"  CID: {cid} (Status: Pinned)")
        elif not found_library_files_pinned and not manifest_paths : # No libraries and no other pins
             pass # Already covered by "No CIDs are currently pinned..."
        elif not other_pinned_cids and found_library_files_pinned:
            click.echo("\nAll pinned items identified correspond to files in your SciPFS libraries.")
        

    except ConnectionError as e:
        click.echo(f"Error: Could not connect to IPFS node. {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"An unexpected error occurred during 'list-pinned': {e}", err=True)
        sys.exit(1)

@cli.command(name="availability")
@click.argument("name")
@click.option("--file", "file_name_option", default=None, help="Check availability only for a specific file in the library.")
@click.option("--verbose", "cmd_verbose_flag", is_flag=True, help="Show raw Peer IDs for each checked CID. Overrides global verbosity for this command.")
@click.option("--timeout", type=int, default=60, show_default=True, help="Timeout in seconds for finding providers for each CID.")
@click.pass_context
def availability_cmd(ctx, name: str, file_name_option: Optional[str], cmd_verbose_flag: bool, timeout: int):
    """Check the network availability of files in a library or a specific file.

    This command uses the IPFS DHT (via the scipfs_go_helper) to find peers
    (providers) for the library's manifest CID and/or specific file CIDs.
    It provides a summary of how many providers are found.
    
    NOTE: This operation queries the IPFS Distributed Hash Table (DHT).
    The performance and success of finding providers can depend on network
    conditions, the IPFS daemon's connectivity, and how widely the content
    is distributed. Ensure your IPFS daemon is running and well-connected.
    """
    # Command specific verbosity overrides global verbosity for its Peer ID list
    show_peer_ids = cmd_verbose_flag or ctx.obj.get('VERBOSE', False)
    
    # The actual logging of INFO messages (like "Searching for providers...")
    # is controlled by the global --verbose flag via scipfs_logger level.

    try:
        ipfs_client = IPFSClient()
    except ConnectionError as e:
        click.echo(f"Error: Could not connect to IPFS. {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error initializing IPFS client: {e}", err=True)
        sys.exit(1)

    try:
        library = Library(name, CONFIG_DIR, ipfs_client)
        if not library.manifest_path.exists():
            click.echo(f"Error: Local manifest for library '{name}' not found at {library.manifest_path}.", err=True)
            click.echo(f"Hint: Did you 'create' or 'join' the library '{name}' first?", err=True)
            sys.exit(1)
        # Ensure library name is loaded from manifest
        actual_library_name = library.name 
    except Exception as e:
        click.echo(f"Error loading library '{name}': {e}", err=True)
        sys.exit(1)

    click.echo(f"--- Availability Report for Library '{actual_library_name}' ---")

    target_cids_map: Dict[str, str] = {} # cid -> description (e.g., "manifest", "file 'x.txt'")
    file_cids_in_report: Set[str] = set()

    if file_name_option:
        file_info = library.manifest.get("files", {}).get(file_name_option)
        if not file_info or not file_info.get("cid"):
            click.echo(f"Error: File '{file_name_option}' not found in library '{actual_library_name}' or missing CID.", err=True)
            sys.exit(1)
        file_cid = file_info["cid"]
        target_cids_map[file_cid] = f"File '{file_name_option}'"
        file_cids_in_report.add(file_cid)
    else:
        if library.manifest_cid:
            target_cids_map[library.manifest_cid] = "Manifest"
        else:
            click.echo(f"Warning: Manifest CID for library '{actual_library_name}' is not available. Cannot check its providers.", err=True)
        
        for f_info in library.list_files():
            if f_info.get("cid"):
                target_cids_map[f_info["cid"]] = f"File '{f_info['name']}'"
                file_cids_in_report.add(f_info["cid"])
            else:
                click.echo(f"Warning: File '{f_info['name']}' in library '{actual_library_name}' is missing a CID. Skipping.", err=True)

    if not target_cids_map:
        click.echo("No CIDs to check for providers. The library might be empty or CIDs are missing.")
        sys.exit(0)

    providers_by_cid: Dict[str, Set[str]] = {}
    all_file_providers_peers: Set[str] = set()
    provider_file_counts: Dict[str, int] = {}

    for cid_to_check, description in target_cids_map.items():
        click.echo(f"Finding providers for {description} ({cid_to_check})... ", nl=False)
        try:
            current_providers = ipfs_client.find_providers(cid_to_check, timeout=timeout)
            providers_by_cid[cid_to_check] = current_providers
            click.echo(f"found {len(current_providers)}.")
            if cid_to_check in file_cids_in_report: # Only count for files for file-specific metrics
                all_file_providers_peers.update(current_providers)
                for peer_id in current_providers:
                    provider_file_counts[peer_id] = provider_file_counts.get(peer_id, 0) + 1
        except Exception as e_find:
            click.echo(f"error: {e_find}. Skipping.", err=True)
            providers_by_cid[cid_to_check] = set() # Store empty set on error

    # Calculate Metrics
    click.echo("\n--- Summary ---")

    if file_name_option: # Specific file mode
        file_cid_to_report = next(iter(target_cids_map.keys())) # Should be only one
        num_prov = len(providers_by_cid.get(file_cid_to_report, set()))
        click.echo(f"{target_cids_map[file_cid_to_report]} (CID: {file_cid_to_report}): Found {num_prov} providers.")
    else: # All files mode
        if library.manifest_cid and library.manifest_cid in providers_by_cid:
            num_manifest_prov = len(providers_by_cid[library.manifest_cid])
            click.echo(f"Manifest (CID: {library.manifest_cid}): Found {num_manifest_prov} providers.")
        elif library.manifest_cid:
            click.echo(f"Manifest (CID: {library.manifest_cid}): Could not retrieve providers (check logs).")

        total_files_in_manifest = len([f for f in library.list_files() if f.get('cid')])
        files_in_report_with_providers = sum(1 for cid in file_cids_in_report if len(providers_by_cid.get(cid, set())) > 0)
        
        if total_files_in_manifest > 0:
            percentage_hosted = (files_in_report_with_providers / total_files_in_manifest) * 100
            click.echo(f"Files in Manifest: {total_files_in_manifest}. Checked {len(file_cids_in_report)} file CIDs.")
            click.echo(f"Files with at least 1 provider: {files_in_report_with_providers} ({percentage_hosted:.2f}% of manifest files with CIDs)." )
        else:
            click.echo("No files with CIDs found in the manifest to check.")

        total_unique_file_providers = len(all_file_providers_peers)
        click.echo(f"Total unique providers across checked files: {total_unique_file_providers}.")
        
        if provider_file_counts:
            avg_files_per_provider = sum(provider_file_counts.values()) / len(provider_file_counts)
            click.echo(f"Average files hosted per unique file provider: {avg_files_per_provider:.2f}.")
        else:
            click.echo("Average files hosted per unique file provider: N/A (no file providers found).")

    if show_peer_ids:
        click.echo("\n--- Verbose: Provider Peer IDs ---")
        for cid_checked, peers in providers_by_cid.items():
            description = target_cids_map.get(cid_checked, f"CID {cid_checked}")
            if peers:
                click.echo(f"Providers for {description}:")
                for peer_id in sorted(list(peers)):
                    click.echo(f"  - {peer_id}")
            else:
                click.echo(f"Providers for {description}: None found or error during lookup.")

    click.echo("\nAvailability check complete.")

@cli.command()
@click.pass_context
def doctor(ctx):
    """Check the SciPFS setup and IPFS daemon connection.

    Provides diagnostic information about your SciPFS environment,
    including versions, IPFS daemon status, and compatibility notes.
    """
    click.echo("--- SciPFS Doctor ---")
    click.echo(f"SciPFS Version: {scipfs_version}")

    # Get API address from config for IPFSClient initialization
    # This uses the global scipfs_config_instance already defined in cli.py
    try:
        api_addr_for_client = scipfs_config_instance.get_api_addr_for_client()
    except Exception as e_conf:
        api_addr_for_client = "/ip4/127.0.0.1/tcp/5001" # Default if config fails
        click.echo(f"Warning: Error getting API address from config: {e_conf}. Using default API address: {api_addr_for_client}.", err=True)

    # Instantiate IPFSClient to use its Go wrapper detection and methods
    # The IPFSClient __init__ will attempt to find and verify the Go wrapper.
    ipfs_client = IPFSClient(addr=api_addr_for_client)

    click.echo("\n--- Go Wrapper Status ---")
    if ipfs_client.is_go_wrapper_available():
        click.echo(f"Go Wrapper ('{ipfs_client.go_wrapper_path}'): Found and Verified")
        click.echo(f"Go Wrapper Version: {ipfs_client.go_wrapper_version}")
    else:
        click.echo(f"Go Wrapper ('{ipfs_client.go_wrapper_executable_name}'): NOT FOUND or FAILED CHECK.")
        if ipfs_client.go_wrapper_error:
            click.echo(f"  Error details: {ipfs_client.go_wrapper_error}")
        click.echo(f"  Ensure '{ipfs_client.go_wrapper_executable_name}' is compiled (run ./build_go_wrapper.sh) and accessible either in the current directory or in your system PATH.")

    click.echo("\n--- IPFS Daemon Status (via Go Wrapper) ---")
    daemon_id = "Unknown"
    daemon_version = "Unknown"
    daemon_addresses_count = 0 # Placeholder, can be expanded if daemon_info provides more

    if ipfs_client.is_go_wrapper_available():
        daemon_info = ipfs_client.get_daemon_info() # This now uses the method from IPFSClient
        if daemon_info:
            daemon_id = daemon_info.get("ID", "N/A")
            # Assuming Go wrapper provides AgentVersion, adjust if key is different (e.g., "Version")
            daemon_version = daemon_info.get("AgentVersion") or daemon_info.get("Version", "N/A") 
            daemon_addresses_count = len(daemon_info.get("Addresses", []))
            click.echo("Status: Successfully queried daemon via Go wrapper.")
            click.echo(f"IPFS Peer ID: {daemon_id}")
            click.echo(f"IPFS Daemon Version: {daemon_version}")
            click.echo(f"Known Addresses: {daemon_addresses_count}") # Example, if Addresses are part of daemon_info
        else:
            click.echo("Status: Failed to get daemon info via Go wrapper.")
            if ipfs_client.go_wrapper_error:
                 click.echo(f"  Error details: {ipfs_client.go_wrapper_error}")
            click.echo("  Ensure IPFS daemon is running and API address ('{ipfs_client.api_addr}') is correct.")
    else:
        click.echo("Status: Skipped daemon check via Go wrapper because wrapper is not available.")

    click.echo("\n--- Compatibility and Update Advice ---")
    click.echo("scipfs is transitioning to a Go-based helper for IPFS interaction.")
    if ipfs_client.is_go_wrapper_available() and ipfs_client.is_go_wrapper_available() != "N/A":
        click.echo(f"Active Go Helper version: {ipfs_client.go_wrapper_version}")
    else:
        click.echo("Go Helper status: Unknown or not found. Build it with ./build_go_wrapper.sh")

    if daemon_version != "Unknown" and daemon_version != "N/A":
        click.echo(f"Detected IPFS Daemon version: {daemon_version}")
        # Add specific compatibility advice if known for the go-kubo-rpc client version used by the wrapper
    else:
        click.echo("Could not determine IPFS Daemon version via Go wrapper.")
    
    click.echo("Ensure your Kubo daemon version is up-to-date and compatible with modern IPFS API standards.")

    click.echo("\nRecommendations:")
    click.echo("1. Ensure the SciPFS Go Helper ('scipfs_go_helper') is built: run ./build_go_wrapper.sh")
    click.echo("2. Keep your Kubo (go-ipfs) daemon updated.")
    click.echo("   - Download from IPFS Distributions: https://dist.ipfs.tech/#kubo")
    click.echo("   - GitHub releases: https://github.com/ipfs/kubo/releases")
    click.echo("3. If 'scipfs availability' or other commands have issues (post-transition):")
    click.echo("   - Check the Go Helper status above.")
    click.echo("   - Ensure your Kubo daemon is compatible with the Go client libraries (typically recent versions).")
    click.echo("   - Consider updating scipfs: 'pip install --upgrade scipfs'.")

    click.echo("\n--- 'availability' Command Check (via Go Wrapper - Conceptual) ---")
    click.echo("The 'availability' command will rely on the Go wrapper's dht.findprovs implementation.")
    click.echo("To test this part of the Go wrapper, you would typically execute a findprovs call via it.")

    click.echo("\nDoctor check complete.")

# Ensure the main guard is present if this script is run directly
if __name__ == '__main__':
    cli()
