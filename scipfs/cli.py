import click
import logging
from pathlib import Path
from .ipfs import IPFSClient, SciPFSGoWrapperError, KuboVersionError, IPFSConnectionError as SciPFSIPFSConnectionError # Added KuboVersionError, SciPFSIPFSConnectionError
from .library import Library
import sys # Import sys for exit
from . import config as scipfs_config # Import the new config module
from . import __version__ as scipfs_version # Import scipfs version
import os # Added for path operations
from typing import Set, Dict, List, Optional # Added Set, Dict, Optional
import subprocess
import json
import re # For parsing version strings

# Minimal IPFS Client for specific internal uses like completion or local listing
class MinimalIPFSClient:
    def add_json(self, _):
        return "dummy_cid_for_internal_use"
    def get_json(self, _):
        return {}
    def pin(self, _):
        pass
    def unpin(self, _):
        pass
    def add_file(self, _):
        return "dummy_cid_for_internal_use"
    def get_file(self, _, __):
        pass
    def resolve_ipns_name(self, _):
        return "/ipfs/dummy_cid_for_internal_use"
    def publish_to_ipns(self, _, __):
        pass
    def generate_ipns_key(self, _):
        return {"Name": "dummy_key", "Id": "dummy_id_for_internal_use"}
    def list_ipns_keys(self):
        return []
    def remove_ipns_key(self, _):
        pass

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
library_logger = logging.getLogger("scipfs.library") # Make sure library_logger is defined if used in complete_file_names

REQUIRED_IPFS_KUBO_VERSION_TUPLE = (0, 23, 0) # Updated required version to a more common one for broader compatibility.
REQUIRED_IPFS_KUBO_VERSION_STR = ".".join(map(str, REQUIRED_IPFS_KUBO_VERSION_TUPLE))

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

@click.group(invoke_without_command=True) # Allow group to be called to run version check
@click.option("--verbose", "verbose_flag", is_flag=True, help="Enable INFO level logging for scipfs operations.")
@click.version_option(version=scipfs_version, help="Show the version and exit.")
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
        scipfs_logger.info("Verbose logging enabled.")
    else:
        scipfs_logger.setLevel(logging.WARNING)

    # If no command is given, cli() itself is invoked.
    # We only initialize IPFSClient if a subcommand is going to be run.
    # The 'init', 'config', 'doctor', and 'version' commands don't need a running IPFS daemon.
    # Other commands do, so we will instantiate client there or check ctx.invoked_subcommand
    if ctx.invoked_subcommand not in [None, 'init', 'config', 'doctor', 'version', 'list-local']:
        try:
            scipfs_logger.info("Initializing IPFSClient...")
            ipfs_client = IPFSClient(
                api_addr=scipfs_config_instance.get_api_addr_for_client(),
                required_version_tuple=REQUIRED_IPFS_KUBO_VERSION_TUPLE
            )
            # Perform version check and connectivity check upon client initialization
            ipfs_client.check_ipfs_daemon() # This method should combine version and connectivity
            ctx.obj['IPFS_CLIENT'] = ipfs_client
            scipfs_logger.info("IPFSClient initialized successfully and daemon checks passed.")
        except SciPFSIPFSConnectionError as e:
            click.echo(f"Error: Could not connect to IPFS API. Ensure your IPFS daemon is running.", err=True)
            click.echo(f"Details: {e}", err=True)
            # Allow specific commands to run without IPFS daemon
            if ctx.invoked_subcommand not in ['init', 'config', 'doctor', 'list-local']:
                 sys.exit(1)
            ctx.obj['IPFS_CLIENT'] = None # Ensure it's None if connection failed
        except KuboVersionError as e:
            click.echo(f"Error: IPFS version mismatch.", err=True)
            click.echo(f"Details: {e}", err=True)
            click.echo(f"SciPFS requires Kubo version {REQUIRED_IPFS_KUBO_VERSION_STR} or compatible.", err=True)
            if ctx.invoked_subcommand not in ['init', 'config', 'doctor']: # doctor might still be useful
                 sys.exit(1)
            ctx.obj['IPFS_CLIENT'] = None 
        except Exception as e: # Catch any other unexpected error during IPFSClient init
            click.echo(f"An unexpected error occurred while initializing IPFS client: {e}", err=True)
            if verbose_flag:
                scipfs_logger.exception("IPFSClient initialization failed")
            if ctx.invoked_subcommand not in ['init', 'config', 'doctor']:
                 sys.exit(1)
            ctx.obj['IPFS_CLIENT'] = None


@cli.command()
@click.pass_context
def init(ctx): # Added ctx
    """Initialize the SciPFS configuration directory.

    This command creates the necessary configuration directory (~/.scipfs)
    if it doesn't already exist. This directory stores local manifest files
    for the libraries you manage.

    Examples:
      scipfs init
    """
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        # Ensure config file is created with defaults if it doesn't exist
        if not scipfs_config_instance.config_file_path.exists():
            scipfs_config_instance._save_config() # Save empty/default config
            click.echo(f"Created default configuration file at {scipfs_config_instance.config_file_path}")
        click.echo(f"Initialized SciPFS configuration at {CONFIG_DIR}")
    except OSError as e:
        click.echo(f"Error initializing configuration directory: {e}", err=True)
        sys.exit(1) # Use sys.exit for cleaner exit codes

@cli.command()
@click.argument("name")
@click.option("--ipns-lifetime", default="24h", show_default=True, help="Set the lifetime for the IPNS record (e.g., '24h', '72h', '30d').")
@click.pass_context 
def create(ctx, name: str, ipns_lifetime: str):
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
    ipfs_client = ctx.obj.get('IPFS_CLIENT')
    if not ipfs_client:
        click.echo("IPFS client not available. Cannot create library. Check IPFS daemon connection and version.", err=True)
        sys.exit(1)
        
    try:
        library = Library(name, CONFIG_DIR, ipfs_client)
        library.create(ipns_record_lifetime=ipns_lifetime)
        
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
    except SciPFSIPFSConnectionError as e: # Catch specific connection error
        click.echo(f"Error connecting to IPFS during 'create': {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"An unexpected error occurred during 'create': {e}", err=True)
        sys.exit(1)

@cli.command()
@click.argument("ipns_name")
@click.pass_context
def join(ctx, ipns_name: str): # Added ctx
    """Join an existing library using its IPNS name.

    Resolves the IPNS name to get the latest manifest CID for the library,
    downloads the manifest from IPFS, and saves it locally. This allows you
    to access and follow a library shared via IPNS.

    Arguments:
      IPNS_NAME: The IPNS name of the library (e.g., /ipns/k51q...).

    Examples:
      scipfs join /ipns/k51q... (use the actual IPNS name)
    """
    ipfs_client = ctx.obj.get('IPFS_CLIENT')
    if not ipfs_client:
        click.echo("IPFS client not available. Cannot join library. Check IPFS daemon connection and version.", err=True)
        sys.exit(1)

    try:
        if not ipns_name.startswith("/ipns/"):
            click.echo("Error: Invalid IPNS name. It should start with '/ipns/'.", err=True)
            sys.exit(1)

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
@click.pass_context
def add(ctx, name: str, file_path: Path): # Added ctx
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
    ipfs_client = ctx.obj.get('IPFS_CLIENT')
    if not ipfs_client:
        click.echo("IPFS client not available. Cannot add file. Check IPFS daemon connection and version.", err=True)
        sys.exit(1)
        
    try:
        username = scipfs_config_instance.get_username()
        if not username:
            click.echo("Error: Username not set. Use 'scipfs config set username <your_username>' first.", err=True)
            sys.exit(1)

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
@click.pass_context
def list_cmd(ctx, name: str): # Added ctx
    """List all files in the specified library.

    Loads the local manifest for the given library name and displays
    the details (name, CID, size) of all files currently listed in it.

    Arguments:
      NAME: The name of the library whose files you want to list.

    Examples:
      scipfs list my-research-papers
    """
    ipfs_client = ctx.obj.get('IPFS_CLIENT')
    # if not ipfs_client: # Allow listing from local manifest even if IPFS daemon is down.
    #     click.echo("Warning: IPFS client not available. Listing from local cache. May not be up-to-date.", err=True)
        
    try:
        # Pass ipfs_client=None if you want to allow pure local listing without IPFS connection
        # For now, assume we might want to check something on IPFS, or keep it consistent
        # If the command *truly* never needs ipfs_client, it can be omitted.
        library = Library(name, CONFIG_DIR, ipfs_client if ipfs_client else MinimalIPFSClient()) # Use mock if no client

        if not library.manifest_path.exists():
            click.echo(f"Error: Library '{name}' not found locally.", err=True)
            click.echo(f"Hint: Use 'scipfs list-local' to see available local libraries, or 'join' an existing one.", err=True)
            sys.exit(1)
            
        files = library.list_files()
        if not files:
            click.echo(f"Library '{name}' is empty or manifest contains no files.")
            return

        click.echo(f"Files in library '{name}' (Manifest CID: {library.manifest_cid or 'N/A'}):")
        # Determine max width for file names for better alignment (optional, for nicer output)
        max_name_len = max(len(f['name']) for f in files) if files else 20
        
        for f_info in files:
            name = f_info.get('name', 'N/A')
            cid = f_info.get('cid', 'N/A')
            size_str = f"{f_info.get('size', 0) / 1024:.2f} KB" if f_info.get('size') else 'Size N/A'
            added_by = f_info.get('added_by', 'N/A')
            added_date = f_info.get('added_date', 'N/A')
            click.echo(f"  {name:<{max_name_len}}  CID: {cid}  Size: {size_str}  Added: {added_by} on {added_date}")
            
    except FileNotFoundError: # Should be caught by manifest_path.exists typically
        click.echo(f"Error: Library '{name}' manifest file not found.", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"An unexpected error occurred while listing files for '{name}': {e}", err=True)
        if ctx.obj.get('VERBOSE'):
            scipfs_logger.exception(f"Failed to list files for library {name}")
        sys.exit(1)

@cli.command()
@click.argument("name")
@click.argument("file_name", required=False, shell_complete=complete_file_names)
@click.argument("output_path", type=click.Path(path_type=Path), required=False)
@click.option("--all", "all_files", is_flag=True, help="Download all files from the library.")
@click.option("--pin", "pin_file_flag", is_flag=True, help="Pin the downloaded file(s) to the local IPFS node.") # Renamed to avoid conflict
@click.pass_context
def get(ctx, name: str, file_name: Optional[str], output_path: Optional[Path], all_files: bool, pin_file_flag: bool): # Added ctx, optional types
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
    ipfs_client = ctx.obj.get('IPFS_CLIENT')
    if not ipfs_client:
        click.echo("IPFS client not available. Cannot get file(s). Check IPFS daemon connection and version.", err=True)
        sys.exit(1)

    if not file_name and not all_files:
        click.echo("Error: Specify a file name, or use --all to download all files.", err=True)
        sys.exit(1)
    if file_name and all_files:
        click.echo("Error: Cannot specify a file name and use --all simultaneously.", err=True)
        sys.exit(1)
        
    try:
        library = Library(name, CONFIG_DIR, ipfs_client)
        if not library.manifest_path.exists():
            click.echo(f"Error: Library '{name}' not found locally.", err=True)
            sys.exit(1)

        files_to_get = []
        if all_files:
            files_to_get = library.list_files()
            if not files_to_get:
                click.echo(f"Library '{name}' is empty. Nothing to download.")
                return
        else: # Single file
            file_info = library.get_file_info(file_name)
            if not file_info:
                click.echo(f"Error: File '{file_name}' not found in library '{name}'.", err=True)
                click.echo(f"Hint: Use 'scipfs list {name}' to see available files.")
                sys.exit(1)
            files_to_get.append(file_info)

        for file_info_item in files_to_get:
            actual_file_name = file_info_item['name']
            cid = file_info_item['cid']
            
            # Determine actual output path
            current_output_path: Path
            if all_files:
                # For --all, output_path is the directory. Create it if it doesn't exist.
                # If output_path is not given for --all, use current directory.
                base_output_dir = output_path if output_path else Path(".")
                base_output_dir.mkdir(parents=True, exist_ok=True)
                current_output_path = base_output_dir / actual_file_name
            else: # Single file
                if output_path:
                    if output_path.is_dir():
                        current_output_path = output_path / actual_file_name
                    else:
                        current_output_path = output_path # User specified full path
                else:
                    current_output_path = Path(actual_file_name) # Download to current dir with original name

            click.echo(f"Downloading '{actual_file_name}' (CID: {cid}) to {current_output_path}...")
            library.get_file(actual_file_name, current_output_path) # get_file_info was called above, direct call to library.get_file
            
            if pin_file_flag:
                click.echo(f"Pinning '{actual_file_name}' (CID: {cid})...")
                try:
                    ipfs_client.pin(cid)
                    click.echo(f"Successfully pinned '{actual_file_name}'.")
                except Exception as e_pin: # Catch specific pinning error from IPFSClient if possible
                    click.echo(f"Error pinning '{actual_file_name}' (CID: {cid}): {e_pin}", err=True)

            click.echo(f"Successfully downloaded '{actual_file_name}' to {current_output_path}.")
            
    except FileNotFoundError as e: # From library operations if manifest/file missing
        click.echo(f"Error during get operation: {e}", err=True)
        sys.exit(1)
    except SciPFSIPFSConnectionError as e:
        click.echo(f"IPFS connection error during get: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"An unexpected error occurred during 'get': {e}", err=True)
        if ctx.obj.get('VERBOSE'):
            scipfs_logger.exception(f"Failed to get file(s) for library {name}")
        sys.exit(1)

@cli.command(name="list-local")
@click.pass_context
def list_local_cmd(ctx): # Added ctx
    """List all libraries with local manifest files."""
    click.echo("Local libraries (found in ~/.scipfs):")
    found_any = False
    local_libraries_data = [] # Use a temporary list to gather data before printing
    try:
        for manifest_file in CONFIG_DIR.glob("*.json"):
            if manifest_file.name == "config.json" or manifest_file.name == "llm_config.json": # Skip config files
                continue

            library_name_stem = manifest_file.stem
            if library_name_stem.endswith("_manifest"):
                library_name = library_name_stem[:-len("_manifest")]
            else:
                library_name = library_name_stem
            
            if not library_name: # Skip if the name is empty after stripping
                if ctx.obj.get('VERBOSE'):
                    click.echo(f"  Skipping potentially malformed manifest file: {manifest_file.name}", err=True)
                continue

            try:
                # Use MinimalIPFSClient as we only need to read manifest data
                lib = Library(library_name, CONFIG_DIR, MinimalIPFSClient())
                # Ensure manifest path exists and manifest was loaded with a name
                if lib.manifest_path.exists() and lib.manifest.get("name"):
                     local_libraries_data.append(f"  - {lib.name} (Manifest CID: {lib.manifest_cid}) [{len(lib.manifest.get('files', []))} file(s)]")
                     found_any = True
                elif lib.manifest_path.exists() and not lib.manifest.get("name"):
                    if ctx.obj.get('VERBOSE'): # Only show this warning if verbose, it can be noisy
                        click.echo(f"  Warning: Manifest file {manifest_file.name} found but seems empty or corrupted. Skipping for matching.", err=True)
            except Exception as e_load_lib:
                if ctx.obj.get('VERBOSE'): # Only show full error if verbose
                    click.echo(f"  Warning: Could not load manifest for {library_name} from {manifest_file.name} for matching: {e_load_lib}", err=True)
        
        if not found_any:
            click.echo("  No local library manifests found.")
        else:
            for entry in local_libraries_data:
                click.echo(entry)

    except Exception as e:
        click.echo(f"Error listing local libraries: {e}", err=True)
        if ctx.obj.get('VERBOSE'):
            scipfs_logger.exception("Failed to list local libraries")
        sys.exit(1)


@cli.command()
@click.argument("name")
@click.pass_context
def update(ctx, name: str): # Added ctx
    """Update a local library by fetching the latest manifest via IPNS."""
    ipfs_client = ctx.obj.get('IPFS_CLIENT')
    if not ipfs_client:
        click.echo("IPFS client not available. Cannot update library. Check IPFS daemon connection and version.", err=True)
        sys.exit(1)
        
    try:
        library = Library(name, CONFIG_DIR, ipfs_client)
        
        if not library.manifest_path.exists():
            click.echo(f"Error: Library '{name}' not found locally. Cannot update.", err=True)
            click.echo(f"Hint: You might need to 'join' it first if you haven't.", err=True)
            sys.exit(1)

        if not library.manifest.get("ipns_name"):
            click.echo(f"Error: Library '{name}' does not have an IPNS name associated with it in the local manifest.", err=True)
            click.echo(f"This library might have been created locally without publishing, or joined incorrectly.", err=True)
            click.echo(f"Automatic updates via IPNS are not possible for this library.", err=True)
            sys.exit(1)
            
        click.echo(f"Updating library '{name}' from IPNS name: {library.manifest.get('ipns_name')}...")
        old_manifest_cid = library.manifest_cid
        library.update_from_ipns() # This method should handle the logic
        
        if library.manifest_cid != old_manifest_cid:
            click.echo(f"Library '{name}' updated successfully.")
            click.echo(f"Old Manifest CID: {old_manifest_cid}")
            click.echo(f"New Manifest CID: {library.manifest_cid}")
        else:
            click.echo(f"Library '{name}' is already up-to-date. Manifest CID: {library.manifest_cid}")
            
    except FileNotFoundError: # IPNS resolution failure within library.update_from_ipns()
        click.echo(f"Error updating library '{name}': Could not resolve its IPNS name. The library might no longer be published or IPNS is slow.", err=True)
        sys.exit(1)
    except SciPFSIPFSConnectionError as e:
        click.echo(f"IPFS connection error during update: {e}", err=True)
        sys.exit(1)
    except ValueError as e: # Other validation errors from library methods
        click.echo(f"Error updating library '{name}': {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"An unexpected error occurred during 'update' for '{name}': {e}", err=True)
        if ctx.obj.get('VERBOSE'):
            scipfs_logger.exception(f"Failed to update library {name}")
        sys.exit(1)

@cli.command()
@click.argument("name")
@click.pass_context
def info(ctx, name: str): # Added ctx
    """Display information about a local library."""
    # ipfs_client = ctx.obj.get('IPFS_CLIENT') # Not strictly needed if just reading local manifest
    
    try:
        # Pass mock client as we are just reading local data.
        library = Library(name, CONFIG_DIR, MinimalIPFSClient()) 
        if not library.manifest_path.exists():
            click.echo(f"Error: Library '{name}' not found locally.", err=True)
            sys.exit(1)
        
        click.echo(f"Information for library: {name}")
        click.echo(f"  Manifest Path: {library.manifest_path}")
        click.echo(f"  Manifest CID (Current): {library.manifest_cid or 'N/A - Not on IPFS or not resolved'}")
        click.echo(f"  IPNS Name (if published): {library.manifest.get('ipns_name', 'N/A')}")
        click.echo(f"  Owner/Creator: {library.manifest.get('owner', 'N/A')}")
        click.echo(f"  Description: {library.manifest.get('description', 'N/A')}")
        click.echo(f"  Number of files: {len(library.manifest.get('files', []))}")
        click.echo(f"  Last Modified (Manifest): {library.manifest.get('last_modified', 'N/A')}")
        
        # Display IPNS key info if this node might be the owner
        if library.manifest.get('ipns_key_name') == name: # Heuristic: key name matches lib name
            ipfs_client_for_keys = ctx.obj.get('IPFS_CLIENT')
            if ipfs_client_for_keys:
                try:
                    keys = ipfs_client_for_keys.list_ipns_keys()
                    matching_key = next((key for key in keys if key.get('Name') == name), None)
                    if matching_key:
                        click.echo(f"  Local IPNS Key ID for '{name}': {matching_key.get('Id')}")
                    else:
                        click.echo(f"  Note: Local IPNS key named '{name}' not found, but manifest suggests it might exist elsewhere.")
                except Exception as e_keys:
                    click.echo(f"  Could not check local IPNS keys: {e_keys}", err=True)
            else:
                 click.echo(f"  (IPFS client not available to check local IPNS keys)")


    except Exception as e:
        click.echo(f"An unexpected error occurred while getting info for '{name}': {e}", err=True)
        if ctx.obj.get('VERBOSE'):
            scipfs_logger.exception(f"Failed to get info for library {name}")
        sys.exit(1)

@cli.group()
@click.pass_context
def config(ctx): # Added ctx
    """Manage SciPFS configuration (e.g., username, IPFS API address)."""
    # This command itself does nothing, subcommands handle actions.
    pass

@config.group("set")
@click.pass_context
def config_set(ctx): # Added ctx
    """Set configuration values."""
    pass

@config_set.command("username")
@click.argument("username_val") # Renamed to avoid conflict with module
@click.pass_context
def set_username_cmd(ctx, username_val: str): # Added ctx, changed username to username_val
    """Set the username for adding files to libraries."""
    try:
        scipfs_config_instance.set_username(username_val)
        click.echo(f"Username set to: {username_val}")
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

@config_set.command("ipfs_api_addr")
@click.argument("api_addr")
@click.pass_context
def set_ipfs_api_addr_cmd(ctx, api_addr: str): # Added ctx
    """Set the IPFS API multiaddress (e.g., /ip4/127.0.0.1/tcp/5001)."""
    try:
        scipfs_config_instance.set_api_addr(api_addr)
        click.echo(f"IPFS API address set to: {api_addr}")
        click.echo("Note: This will be used for the next SciPFS command invocation.")
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

@config.command("show")
@click.pass_context
def config_show(ctx): # Added ctx
    """Show the current configuration."""
    click.echo("Current SciPFS Configuration:")
    click.echo(f"  Config file location: {scipfs_config_instance.config_file_path}")
    username = scipfs_config_instance.get_username()
    api_addr = scipfs_config_instance.get_api_addr_for_client()
    username_display = username if username else "Not set (use 'scipfs config set username <name>')"
    click.echo(f"  Username: {username_display}")
    click.echo(f"  IPFS API Address: {api_addr if api_addr else 'Using default (currently /ip4/127.0.0.1/tcp/5001)'}")
    # Add other config display as needed


@cli.group()
@click.pass_context
def pin(ctx): # Added ctx
    """Manage IPFS pins relevant to SciPFS (files, CIDs, libraries)."""
    # Requires IPFS client
    if not ctx.obj.get('IPFS_CLIENT'):
        click.echo("IPFS client not available. Pin commands require a running IPFS daemon.", err=True)
        sys.exit(1)

@pin.command(name="cid")
@click.argument("cid_string")
@click.pass_context
def pin_cid(ctx, cid_string: str): # Added ctx
    """Pin a specific IPFS CID."""
    ipfs_client = ctx.obj.get('IPFS_CLIENT')
    # Already checked in parent group, but being explicit if called directly (though click usually prevents this)
    if not ipfs_client: 
        click.echo("IPFS client not available.", err=True)
        sys.exit(1)
        
    try:
        click.echo(f"Attempting to pin CID: {cid_string}...")
        ipfs_client.pin(cid_string)
        click.echo(f"Successfully pinned CID: {cid_string}")
    except SciPFSIPFSConnectionError as e:
        click.echo(f"Error pinning CID {cid_string}: IPFS connection failed. {e}", err=True)
        sys.exit(1)
    except Exception as e: # More specific errors from ipfs_client.pin would be good
        click.echo(f"Error pinning CID {cid_string}: {e}", err=True)
        if ctx.obj.get('VERBOSE'):
            scipfs_logger.exception(f"Failed to pin CID {cid_string}")
        sys.exit(1)

@pin.command(name="file")
@click.argument("file_path_arg", type=click.Path(exists=True, dir_okay=False, readable=True, path_type=Path)) # Renamed
@click.pass_context
def pin_file(ctx, file_path_arg: Path): # Added ctx, renamed
    """Add a file to IPFS and pin it (does not add to a SciPFS library)."""
    ipfs_client = ctx.obj.get('IPFS_CLIENT')
    if not ipfs_client:
        click.echo("IPFS client not available.", err=True)
        sys.exit(1)

    try:
        click.echo(f"Adding and pinning file: {file_path_arg}...")
        # The IPFSClient.add_file method should handle both adding and pinning implicitly or have an option.
        # Assuming add_file pins by default or we add a pin_after_add flag.
        # For this command, we want to ensure it's pinned.
        file_cid = ipfs_client.add_file(file_path_arg, pin=True) # Explicitly request pinning
        
        if file_cid:
            click.echo(f"File '{file_path_arg.name}' added to IPFS with CID: {file_cid}")
            click.echo(f"Successfully pinned CID: {file_cid}")
        else:
            click.echo(f"Failed to add or pin file {file_path_arg}. No CID returned.", err=True)
            sys.exit(1)
            
    except SciPFSIPFSConnectionError as e:
        click.echo(f"Error adding/pinning file {file_path_arg}: IPFS connection failed. {e}", err=True)
        sys.exit(1)
    except FileNotFoundError: # Should be caught by click.Path(exists=True)
        click.echo(f"Error: File not found at {file_path_arg}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error adding/pinning file {file_path_arg}: {e}", err=True)
        if ctx.obj.get('VERBOSE'):
            scipfs_logger.exception(f"Failed to pin file {file_path_arg}")
        sys.exit(1)

@pin.command(name="library")
@click.argument("library_name_arg") # Renamed
@click.pass_context
def pin_library(ctx, library_name_arg: str): # Added ctx, renamed
    """Pin all files and the manifest of a specified local library."""
    ipfs_client = ctx.obj.get('IPFS_CLIENT')
    if not ipfs_client:
        click.echo("IPFS client not available.", err=True)
        sys.exit(1)

    try:
        library = Library(library_name_arg, CONFIG_DIR, ipfs_client)
        if not library.manifest_path.exists():
            click.echo(f"Error: Library '{library_name_arg}' not found locally.", err=True)
            click.echo(f"Hint: Did you 'create' or 'join' the library '{library_name_arg}' first?", err=True)
            sys.exit(1)
        
        click.echo(f"Pinning library '{library_name_arg}'...")
        
        # 1. Pin the manifest itself
        if library.manifest_cid:
            click.echo(f"  Pinning manifest (CID: {library.manifest_cid})...")
            try:
                ipfs_client.pin(library.manifest_cid)
                click.echo(f"  Manifest pinned successfully.")
            except Exception as e_pin_manifest:
                click.echo(f"  Error pinning manifest (CID: {library.manifest_cid}): {e_pin_manifest}", err=True)
        else:
            click.echo(f"  Skipping manifest pinning: No manifest CID found (library might be empty or not on IPFS).", err=True)

        # 2. Pin all files in the library
        files_in_library = library.list_files()
        if not files_in_library:
            click.echo(f"  Library '{library_name_arg}' contains no files to pin.")
        else:
            click.echo(f"  Pinning {len(files_in_library)} file(s) in library '{library_name_arg}':")
            success_pins = 0
            error_pins = 0
            for file_info in files_in_library:
                file_cid_to_pin = file_info.get('cid')
                file_name_to_pin = file_info.get('name')
                if file_cid_to_pin:
                    click.echo(f"    Pinning '{file_name_to_pin}' (CID: {file_cid_to_pin})...", nl=False)
                    try:
                        ipfs_client.pin(file_cid_to_pin)
                        click.echo(" Success.")
                        success_pins += 1
                    except Exception as e_pin_file:
                        click.echo(f" Error: {e_pin_file}", err=True)
                        error_pins += 1
                else:
                    click.echo(f"    Skipping '{file_name_to_pin}': No CID found.", err=True)
                    error_pins +=1
            
            click.echo(f"  Finished pinning files: {success_pins} succeeded, {error_pins} failed/skipped.")

        click.echo(f"Library '{library_name_arg}' pinning process complete.")

    except SciPFSIPFSConnectionError as e:
        click.echo(f"Error pinning library {library_name_arg}: IPFS connection failed. {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error pinning library {library_name_arg}: {e}", err=True)
        if ctx.obj.get('VERBOSE'):
            scipfs_logger.exception(f"Failed to pin library {library_name_arg}")
        sys.exit(1)


@cli.command(name="list-pinned")
@click.option("--raw", is_flag=True, help="Show only raw CIDs without library matching.")
@click.option("--timeout", default=10, show_default=True, help="Timeout in seconds for IPFS pin ls command.")
@click.pass_context
def list_pinned_cmd(ctx, raw: bool, timeout: int): # Added ctx
    """List all CIDs pinned by the local IPFS node.
    Optionally attempts to match CIDs to known local SciPFS libraries and files.
    """
    ipfs_client = ctx.obj.get('IPFS_CLIENT')
    if not ipfs_client:
        click.echo("IPFS client not available. Cannot list pinned items. Check IPFS daemon connection and version.", err=True)
        sys.exit(1)

    try:
        click.echo(f"Fetching pinned CIDs from local IPFS node (timeout: {timeout}s)...")
        # Use the direct method from IPFSClient which should handle the go-wrapper call
        pinned_cids_map = ipfs_client.list_pinned_cids(timeout=timeout) # Expects a dict {cid_str: {'Type': 'recursive/direct/etc'}}

        if not pinned_cids_map:
            click.echo("No CIDs are currently pinned by the local IPFS node.")
            return

        click.echo(f"Found {len(pinned_cids_map)} pinned CIDs (recursive pins count as one).")

        if raw:
            click.echo("Raw pinned CIDs (and their pin types):")
            for cid_str, pin_info in pinned_cids_map.items():
                click.echo(f"  - {cid_str} (Type: {pin_info.get('Type', 'Unknown')})")
            return

        # --- Match CIDs to libraries and files ---
        click.echo("\nMatching pinned CIDs to local SciPFS libraries...")
        matched_cids = set()
        # Load all local library manifests
        local_libraries: List[Library] = []
        for manifest_file in CONFIG_DIR.glob("*.json"):
            if manifest_file.name in ["config.json", "llm_config.json"]: continue

            library_name_stem = manifest_file.stem
            if library_name_stem.endswith("_manifest"):
                library_name = library_name_stem[:-len("_manifest")]
            else:
                library_name = library_name_stem
            
            if not library_name: # Skip if the name is empty after stripping
                if ctx.obj.get('VERBOSE'):
                    click.echo(f"  Skipping potentially malformed manifest file: {manifest_file.name}", err=True)
                continue

            try:
                # Use MinimalIPFSClient as we only need to read manifest data
                lib = Library(library_name, CONFIG_DIR, MinimalIPFSClient())
                # Ensure manifest path exists and manifest was loaded with a name
                if lib.manifest_path.exists() and lib.manifest.get("name"):
                     local_libraries.append(lib)
                elif lib.manifest_path.exists() and not lib.manifest.get("name"):
                    if ctx.obj.get('VERBOSE'): # Only show this warning if verbose, it can be noisy
                        click.echo(f"  Warning: Manifest file {manifest_file.name} found but seems empty or corrupted. Skipping for matching.", err=True)
            except Exception as e_load_lib:
                if ctx.obj.get('VERBOSE'): # Only show full error if verbose
                    click.echo(f"  Warning: Could not load manifest for {library_name} from {manifest_file.name} for matching: {e_load_lib}", err=True)
                else:
                    click.echo(f"  Warning: Could not load manifest {manifest_file.name} for matching. Run with --verbose for details.", err=True)
        
        if not local_libraries:
            click.echo("No local libraries found to match against CIDs.") # Slightly more specific message
        
        pinned_by_library: Dict[str, Dict[str, List[Dict[str,str]]]] = {} # lib_name: {"manifest": [], "files": []}

        for lib_instance in local_libraries:
            lib_name = lib_instance.name
            pinned_by_library[lib_name] = {"manifest": [], "files": []}

            # Check library manifest CID
            if lib_instance.manifest_cid and lib_instance.manifest_cid in pinned_cids_map:
                pin_type = pinned_cids_map[lib_instance.manifest_cid].get('Type', 'Unknown')
                pinned_by_library[lib_name]["manifest"].append({
                    "cid": lib_instance.manifest_cid, "type": pin_type
                })
                matched_cids.add(lib_instance.manifest_cid)
            
            # Check CIDs of files in the library
            for file_data in lib_instance.list_files():
                file_cid = file_data.get("cid")
                file_name = file_data.get("name", "Unknown File")
                if file_cid and file_cid in pinned_cids_map:
                    pin_type = pinned_cids_map[file_cid].get('Type', 'Unknown')
                    pinned_by_library[lib_name]["files"].append({
                        "name": file_name, "cid": file_cid, "type": pin_type
                    })
                    matched_cids.add(file_cid)

        # Display results
        any_lib_matches = False
        for lib_name, items in pinned_by_library.items():
            if items["manifest"] or items["files"]:
                any_lib_matches = True
                click.echo(f"\nLibrary: {lib_name}")
                if items["manifest"]:
                    for m_info in items["manifest"]:
                        click.echo(f"  - Manifest: {m_info['cid']} (PinType: {m_info['type']})")
                if items["files"]:
                    click.echo(f"  - Files ({len(items['files'])}):")
                    for f_info in items["files"]:
                        click.echo(f"    - Name: {f_info['name']}, CID: {f_info['cid']} (PinType: {f_info['type']})")
        
        if not any_lib_matches and local_libraries:
            click.echo("No pinned CIDs matched known SciPFS library manifests or files.")

        # List remaining unmatched CIDs
        unmatched_cids = set(pinned_cids_map.keys()) - matched_cids
        if unmatched_cids:
            click.echo("\nOther pinned CIDs (not directly associated with local SciPFS library contents):")
            for cid_str in sorted(list(unmatched_cids)): # Sort for consistent output
                pin_type = pinned_cids_map[cid_str].get('Type', 'Unknown')
                click.echo(f"  - {cid_str} (Type: {pin_type})")
        elif not any_lib_matches and not local_libraries : # No local libraries and no unmatched (means no pins at all)
             pass # Already handled by initial "No CIDs are currently pinned"
        else:
             click.echo("\nAll pinned CIDs are associated with known SciPFS library contents.")


    except SciPFSIPFSConnectionError as e:
        click.echo(f"Error listing pinned CIDs: IPFS connection failed. {e}", err=True)
        sys.exit(1)
    except SciPFSGoWrapperError as e: # Specific error for scipfs_go_helper issues
        click.echo(f"Error executing IPFS command via wrapper: {e}", err=True)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        click.echo(f"Error: Timeout ({timeout}s) reached while listing pinned CIDs. Your IPFS node might be busy or have many pins.", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"An unexpected error occurred while listing pinned CIDs: {e}", err=True)
        if ctx.obj.get('VERBOSE'):
            scipfs_logger.exception("Failed to list pinned CIDs")
        sys.exit(1)


@cli.command(name="availability")
@click.argument("name")
@click.option("--file", "file_name_option", default=None, help="Check availability only for a specific file in the library.")
@click.option("--verbose", "cmd_verbose_flag", is_flag=True, help="Show raw Peer IDs for each checked CID. Overrides global verbosity for this command.")
@click.option("--timeout", type=int, default=60, show_default=True, help="Timeout in seconds for finding providers for each CID.")
@click.pass_context
def availability_cmd(ctx, name: str, file_name_option: Optional[str], cmd_verbose_flag: bool, timeout: int):
    """Check the network availability of files in a library.
    This command uses 'ipfs dht findprovs' to find peers providing the content.
    It can take a significant amount of time depending on the network and number of files.
    """
    ipfs_client = ctx.obj.get('IPFS_CLIENT')
    if not ipfs_client:
        click.echo("IPFS client not available. Cannot check availability. Check IPFS daemon connection and version.", err=True)
        sys.exit(1)

    is_global_verbose = ctx.obj.get('VERBOSE', False)
    # Command specific verbose overrides global for this command's IPFSClient use if needed, or just for output
    final_verbose_output = cmd_verbose_flag or is_global_verbose 

    try:
        library = Library(name, CONFIG_DIR, ipfs_client)
        if not library.manifest_path.exists():
            click.echo(f"Error: Library '{name}' not found locally.", err=True)
            sys.exit(1)

        cids_to_check: List[Dict[str, str]] = [] # List of {"name": str, "cid": str}

        # Check manifest first
        if library.manifest_cid:
            cids_to_check.append({"name": f"Manifest for {name}", "cid": library.manifest_cid})
        else:
            click.echo(f"Warning: Library '{name}' does not have a root manifest CID. Cannot check its availability.", err=True)

        if file_name_option:
            file_info = library.get_file_info(file_name_option)
            if not file_info or not file_info.get('cid'):
                click.echo(f"Error: File '{file_name_option}' not found in library '{name}' or has no CID.", err=True)
                sys.exit(1)
            cids_to_check.append({"name": file_info['name'], "cid": file_info['cid']})
        else: # All files
            files_in_lib = library.list_files()
            if not files_in_lib and not library.manifest_cid : # No manifest and no files.
                 click.echo(f"Library '{name}' is empty and has no manifest CID. Nothing to check for availability.")
                 return
            for f_info in files_in_lib:
                if f_info.get('cid'):
                    cids_to_check.append({"name": f_info['name'], "cid": f_info['cid']})
        
        if not cids_to_check:
            click.echo(f"No CIDs found to check for availability in library '{name}'.")
            return

        click.echo(f"Checking availability for {len(cids_to_check)} CID(s) in library '{name}' (Timeout per CID: {timeout}s). This may take a while...")
        
        all_cids_available = True
        total_providers_found = 0

        for item_to_check in cids_to_check:
            item_name = item_to_check['name']
            item_cid = item_to_check['cid']
            click.echo(f"\n  Checking: {item_name} (CID: {item_cid})")
            
            try:
                providers = ipfs_client.find_providers(item_cid, timeout=timeout) # Should return list of Peer IDs
                
                if providers:
                    click.echo(f"    Found {len(providers)} provider(s) for {item_name}.")
                    total_providers_found += len(providers)
                    if final_verbose_output:
                        for peer_id in providers:
                            click.echo(f"      - {peer_id}")
                else:
                    click.echo(f"    No providers found for {item_name} (CID: {item_cid}) within {timeout}s.")
                    all_cids_available = False # Mark that at least one CID was not found
            except subprocess.TimeoutExpired:
                click.echo(f"    Timeout ({timeout}s) reached while finding providers for {item_name} (CID: {item_cid}).")
                all_cids_available = False
            except SciPFSGoWrapperError as e_prov: # Errors from the wrapper during findprovs
                click.echo(f"    Error finding providers for {item_name} (CID: {item_cid}): {e_prov}", err=True)
                all_cids_available = False
            except Exception as e_general: # Other unexpected errors
                click.echo(f"    An unexpected error occurred while finding providers for {item_name} (CID: {item_cid}): {e_general}", err=True)
                if final_verbose_output: # Or ctx.obj.get('VERBOSE')
                    scipfs_logger.exception(f"Provider check failed for {item_cid}")
                all_cids_available = False
        
        click.echo("\n--- Availability Summary ---")
        if total_providers_found > 0 and all_cids_available:
            click.echo(f"All checked CIDs in library '{name}' appear to be available from at least one provider.")
        elif total_providers_found > 0 and not all_cids_available:
            click.echo(f"Some CIDs in library '{name}' were found, but others were not available or timed out.")
            click.echo("Review the log above for details on which CIDs had issues.")
        else: # total_providers_found == 0
            click.echo(f"No providers were found for any of the checked CIDs in library '{name}'.")
            click.echo("The content may not be widely available or seeded on the IPFS network.")

    except SciPFSIPFSConnectionError as e:
        click.echo(f"Error checking availability for library '{name}': IPFS connection failed. {e}", err=True)
        sys.exit(1)
    except FileNotFoundError: # Library manifest not found
         click.echo(f"Error: Library '{name}' manifest file not found.", err=True)
         sys.exit(1)
    except Exception as e:
        click.echo(f"An unexpected error occurred during 'availability' for '{name}': {e}", err=True)
        if ctx.obj.get('VERBOSE'): # Use global verbose for unexpected errors in the command itself
            scipfs_logger.exception(f"Failed to check availability for library {name}")
        sys.exit(1)


@cli.command()
@click.pass_context
def doctor(ctx):
    """Run diagnostic checks for SciPFS and its dependencies (like IPFS daemon)."""
    click.echo("Running SciPFS Doctor...")
    verbose_mode = ctx.obj.get('VERBOSE', False)
    all_ok = True

    # 1. Check SciPFS Configuration Directory & File
    click.echo("\n1. Checking SciPFS Configuration...")
    try:
        if not CONFIG_DIR.exists():
            click.echo(f"  [FAIL] Configuration directory {CONFIG_DIR} does not exist.")
            click.echo(f"         Run 'scipfs init' to create it.")
            all_ok = False
        else:
            click.echo(f"  [OK] Configuration directory exists: {CONFIG_DIR}")
            if not scipfs_config_instance.config_file_path.exists():
                click.echo(f"  [WARN] Main config file {scipfs_config_instance.config_file_path} does not exist.")
                click.echo(f"         It will be created with defaults on first use or by 'scipfs init'.")
                # all_ok = False # Not critical enough to fail all_ok
            else:
                click.echo(f"  [OK] Main config file exists: {scipfs_config_instance.config_file_path}")
                # Optionally load and validate config structure here
                try:
                    _ = scipfs_config_instance.get_username() # Try accessing a value
                    _ = scipfs_config_instance.get_api_addr_for_client()
                    click.echo(f"  [OK] Configuration file is readable.")
                except Exception as e_conf_read:
                    click.echo(f"  [FAIL] Error reading configuration file {scipfs_config_instance.config_file_path}: {e_conf_read}", err=True)
                    all_ok = False
        
        username = scipfs_config_instance.get_username()
        if username:
            click.echo(f"  [INFO] Username configured: {username}")
        else:
            click.echo(f"  [WARN] Username not configured. Some commands (like 'add') will fail.")
            click.echo(f"         Use 'scipfs config set username <your_username>'.")
            # all_ok = False # Not a global failure for all commands

    except Exception as e_cfg:
        click.echo(f"  [FAIL] Error checking SciPFS configuration: {e_cfg}", err=True)
        all_ok = False

    # 2. Check IPFS Daemon (Connectivity and Version)
    # This part relies on IPFSClient initialization, which is now done in the main cli() context.
    # We can try to get it from there, or re-initialize for doctor specifically if needed.
    click.echo("\n2. Checking IPFS Daemon...")
    ipfs_client_from_ctx = ctx.obj.get('IPFS_CLIENT') 
    
    if ipfs_client_from_ctx: # If client was initialized successfully by the group invoke
        click.echo(f"  [OK] IPFS daemon connected successfully via API: {ipfs_client_from_ctx.api_addr}")
        # Version check already done by IPFSClient constructor if it reached here
        click.echo(f"  [INFO] Connected IPFS daemon version: {ipfs_client_from_ctx.get_version_str() or 'Unknown'}") # Assuming get_version_str() exists
        click.echo(f"  [INFO] SciPFS requires Kubo: {REQUIRED_IPFS_KUBO_VERSION_STR} or compatible.")
        # The check_ipfs_daemon in IPFSClient would have raised error if version incompatible
    else: # IPFS_CLIENT is None, means it failed in the group context or was skipped. Try to init here for doctor.
        click.echo(f"  Attempting to connect to IPFS daemon for diagnostics...")
        try:
            temp_ipfs_client = IPFSClient(
                api_addr=scipfs_config_instance.get_api_addr_for_client(),
                required_version_tuple=REQUIRED_IPFS_KUBO_VERSION_TUPLE
            )
            temp_ipfs_client.check_ipfs_daemon() # This will do version and connectivity
            click.echo(f"  [OK] IPFS daemon connected successfully via API: {temp_ipfs_client.api_addr}")
            actual_version_str = temp_ipfs_client.get_version_str()
            click.echo(f"  [OK] Connected IPFS daemon version: {actual_version_str}")
            
            # Perform the version comparison again for clarity in doctor, even if IPFSClient does it
            if temp_ipfs_client.check_version(REQUIRED_IPFS_KUBO_VERSION_TUPLE):
                 click.echo(f"  [OK] IPFS version ({actual_version_str}) is compatible with required ({REQUIRED_IPFS_KUBO_VERSION_STR}).")
            else:
                 click.echo(f"  [FAIL] IPFS version ({actual_version_str}) is NOT compatible with required ({REQUIRED_IPFS_KUBO_VERSION_STR}).", err=True)
                 all_ok = False

        except SciPFSIPFSConnectionError as e_conn:
            click.echo(f"  [FAIL] Could not connect to IPFS API at {scipfs_config_instance.get_api_addr_for_client()}.", err=True)
            click.echo(f"         Details: {e_conn}", err=True)
            click.echo(f"         Please ensure your IPFS daemon (Kubo) is running and accessible.")
            all_ok = False
        except KuboVersionError as e_ver:
            click.echo(f"  [FAIL] IPFS version issue: {e_ver}", err=True)
            click.echo(f"         SciPFS requires Kubo version {REQUIRED_IPFS_KUBO_VERSION_STR} or compatible.", err=True)
            all_ok = False
        except Exception as e_ipfs_init:
            click.echo(f"  [FAIL] An unexpected error occurred while checking IPFS daemon: {e_ipfs_init}", err=True)
            if verbose_mode:
                scipfs_logger.exception("Doctor: IPFS daemon check failed")
            all_ok = False

    # 3. Check scipfs_go_helper
    click.echo("\n3. Checking scipfs_go_helper utility...")
    try:
        # This assumes IPFSClient uses scipfs_go_helper internally for some operations like 'id' or 'version'
        # Or we have a direct way to test the helper.
        # For now, let's assume a successful IPFSClient init (if it uses the helper) is a good sign.
        # A more direct test:
        if ipfs_client_from_ctx: # If we have a working client, it implies go_helper is likely okay if used by client.
             helper_path = getattr(ipfs_client_from_ctx, 'go_wrapper_path', "Unknown path") # If IPFSClient stores it
             click.echo(f"  [INFO] IPFSClient is initialized, which may use the go_helper ({helper_path}).")
             # A direct lightweight command through go_helper if possible
             try:
                 # Example: ipfs_client_from_ctx._run_go_wrapper_cmd(['version']) # If such internal method exists and is safe
                 # For now, we'll rely on the fact that IPFSClient() didn't fail catastrophically
                 # if it depends on the go_helper for basic ops like version.
                 # A more robust check for the helper itself:
                 go_helper_exe_name = "scipfs_go_helper" # Or scipfs_go_wrapper
                 # Attempt to find it using shutil.which or by checking common paths if needed.
                 # For simplicity, assume it's in PATH or alongside the Python script if packaged that way.
                 # This is a placeholder for a more robust check:
                 try:
                     # Try running the helper directly with a harmless command like --version if it supports it
                     # This is pseudocode as the actual command for go_helper version is unknown
                     # result = subprocess.run([go_helper_exe_name, "--version"], capture_output=True, text=True, check=False, timeout=5)
                     # if result.returncode == 0 and "version" in result.stdout.lower():
                     #    click.echo(f"  [OK] {go_helper_exe_name} seems responsive.")
                     # else:
                     #    click.echo(f"  [WARN] {go_helper_exe_name} did not respond as expected (stdout: {result.stdout}, stderr: {result.stderr}).")
                     # For now, assume if IPFSClient works, the helper it uses is fine.
                     # A more direct check would be to see if the `scipfs_go_helper` or `scipfs_go_wrapper` file exists
                     # and is executable.
                     expected_helper_path_py = Path(sys.modules['scipfs.ipfs'].__file__).parent.parent / "scipfs_go_helper"
                     expected_helper_path_wrapper = Path(sys.modules['scipfs.ipfs'].__file__).parent.parent / "scipfs_go_wrapper"

                     if expected_helper_path_py.exists() and os.access(expected_helper_path_py, os.X_OK):
                         click.echo(f"  [OK] Found executable helper: {expected_helper_path_py}")
                     elif expected_helper_path_wrapper.exists() and os.access(expected_helper_path_wrapper, os.X_OK):
                         click.echo(f"  [OK] Found executable wrapper: {expected_helper_path_wrapper}")
                     else:
                         click.echo(f"  [WARN] scipfs_go_helper/scipfs_go_wrapper executable not found at expected locations near package.")
                         click.echo(f"         Searched: {expected_helper_path_py}, {expected_helper_path_wrapper}")
                         click.echo(f"         If IPFS commands are failing, this might be the cause.")
                         # all_ok = False # This might be a soft warning if not all commands use it.
                 except Exception as e_helper_check:
                     click.echo(f"  [WARN] Could not definitively check scipfs_go_helper: {e_helper_check}")

             except Exception as e_helper:
                 click.echo(f"  [WARN] Could not verify scipfs_go_helper status via IPFSClient: {e_helper}", err=True)
        else: # No IPFS client from context
            click.echo(f"  [INFO] IPFS client not initialized, skipping scipfs_go_helper check via client.")
            # Direct check as above could still be performed here.

    except Exception as e_goh:
        click.echo(f"  [FAIL] Error checking scipfs_go_helper: {e_goh}", err=True)
        all_ok = False


    # Summary
    click.echo("\n--- Doctor Summary ---")
    if all_ok:
        click.echo("[SUCCESS] All checks passed. SciPFS appears to be configured correctly.")
        click.echo("If you still experience issues, try running with --verbose and check logs.")
    else:
        click.echo("[FAIL] Some checks failed. Please review the messages above to diagnose and fix issues.", err=True)
        sys.exit(1)

# Entry point for script execution (e.g., if run via `python -m scipfs.cli`)
if __name__ == '__main__':
    cli(obj={}) # Pass an empty object for context if run directly
