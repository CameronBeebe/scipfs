# SciPFS

**SciPFS** is a command-line tool designed to help small groups and communities manage decentralized file libraries on the InterPlanetary File System (IPFS). It allows users to create, join, and manage libraries of files (such as PDFs, text files, or other types) that are shared and hosted across the group.

IN PROGRESS: We are adding LLM integration to use your API keys, with intelligent librarian, management, and other uses.

---

## Table of Contents

1. [Installation](#installation)
2. [Setting Up IPFS](#setting-up-ipfs)
   - [Installing IPFS](#installing-ipfs)
   - [Initializing IPFS](#initializing-ipfs)
   - [Starting the IPFS Daemon](#starting-the-ipfs-daemon)
3. [Understanding Content IDs (CIDs) and IPNS](#understanding-content-ids-cids-and-ipns)
   - [What is a CID?](#what-is-a-cid)
   - [What is IPNS?](#what-is-ipns)
   - [How CIDs and IPNS are Used in SciPFS](#how-cids-and-ipns-are-used-in-scipfs)
4. [Using SciPFS](#using-scipfs)
   - [Initializing SciPFS](#initializing-scipfs)
   - [Configuring Username](#configuring-username)
   - [Creating a Library](#creating-a-library)
   - [Adding Files to a Library](#adding-files-to-a-library)
   - [Listing Files in a Library](#listing-files-in-a-library)
   - [Downloading Files from a Library](#downloading-files-from-a-library)
   - [Joining an Existing Library](#joining-an-existing-library)
   - [Updating a Library (Getting Latest Changes)](#updating-a-library-getting-latest-changes)
   - [Viewing Library Info](#viewing-library-info)
   - [Listing Local Libraries](#listing-local-libraries)
   - [Listing Pinned Library Files](#listing-pinned-library-files)
5. [Group Coordination (via IPNS)](#group-coordination-via-ipns)
   - [Sharing the Library (via IPNS Name)](#sharing-the-library-via-ipns-name)
   - [How Library Updates Work](#how-library-updates-work)
   - [Pinning Content for Availability](#pinning-content-for-availability)
6. [Running Tests](#running-tests)
7. [Debugging Common Issues](#debugging-common-issues)
   - [Can't Connect to IPFS Node](#cant-connect-to-ipfs-node)
   - [Files Not Found in Library](#files-not-found-in-library)
   - [Manifest Not Updating / Changes Not Visible](#manifest-not-updating--changes-not-visible)
8. [FAQ](#faq)
9. [Contributing](#contributing)

---

## Installation

To use SciPFS, you need to have Python 3.8+ installed, along with a running IPFS daemon. Follow these steps to install SciPFS:

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/CameronBeebe/scipfs.git
    cd scipfs
    ```

2.  **Install the package:**

    You can install the package in two ways:

    *   **Regular install:**
        ```bash
        pip install .
        ```
        This will install the package as it is.

    *   **Editable (developer) install:**
        ```bash
        pip install -e .
        ```
        This is recommended if you plan to modify the code or contribute to development. It installs the package in a way that your changes to the source code are immediately reflected without needing to reinstall.

3. **Ensure IPFS is installed and running** (see [Setting Up IPFS](#setting-up-ipfs)).

**Note on Go Helper Compatibility:**

The SciPFS Go helper binary (`scipfs_go_helper`) is required for some operations (like `add_file` and `pin`).
This binary is **not** included directly in the repository. You will need to build it from source after cloning the project.

- **Operating System & Architecture:** The Go toolchain supports cross-compilation, but the provided `build_go_wrapper.sh` script is primarily set up for building on the current system. The Go source `scipfs_go_wrapper.go` should be compatible with standard Go environments (typically macOS, Linux, Windows on common architectures like amd64, arm64).
- **Build Instructions:** Run the `build_go_wrapper.sh` script located in the project root:
  ```bash
  ./build_go_wrapper.sh
  ```
  This will compile `scipfs_go_wrapper.go` and produce the `scipfs_go_helper` executable in the project root.

Support for distributing pre-compiled binaries for various platforms or more integrated build steps during package installation is planned for future releases.

---

## Setting Up IPFS

SciPFS relies on a local IPFS node to function. You must have the IPFS daemon running whenever you use SciPFS. Below are the steps to set up IPFS on your machine.

### Installing IPFS

1. **Download IPFS**:
   - Visit the [IPFS installation page](https://docs.ipfs.io/install/command-line/#install-official-binary-distributions) and follow the instructions for your operating system.
   - Alternatively, use package managers:
     - **macOS**: `brew install ipfs`
     - **Ubuntu**: `snap install ipfs`

2. **Verify Installation**:
   ```bash
   ipfs --version
   ```
   - You should see the IPFS version number if installed correctly.

### Initializing IPFS

Once IPFS is installed, initialize it:

```bash
ipfs init
```

This sets up the IPFS repository on your machine.

### Starting the IPFS Daemon

To interact with IPFS, start the IPFS daemon:

```bash
ipfs daemon
```

- The daemon must be running in the background while using SciPFS.
- Stop it with `Ctrl+C` when not in use.

**Note**: If you encounter issues, ensure the daemon is running and no other processes are using the same ports.

### IPFS Version Compatibility and Go Helper

SciPFS now exclusively uses a custom Go program (`scipfs_go_helper`) to communicate with your IPFS daemon. This approach replaces the previous Python-based `ipfshttpclient` library.

- **Go Helper (`scipfs_go_helper`)**: This executable is crucial for all IPFS operations within SciPFS. You must build it from the provided Go source code (`scipfs_go_wrapper.go`) using the `./build_go_wrapper.sh` script after cloning the repository. Ensure this helper is in your PATH or the current working directory when running `scipfs`.
- **Kubo (IPFS Daemon) Compatibility**: The `scipfs_go_helper` interacts with your IPFS daemon (typically Kubo, formerly go-ipfs) via its HTTP API.
    - **Required Version**: SciPFS requires **Kubo version 0.34.1 or newer**. The `scipfs_go_helper` will perform a version check upon startup and will exit with an error if an older, incompatible version of Kubo is detected.
    - **Recommendation**: Keep your Kubo daemon updated to version 0.34.1 or a more recent stable release. If you encounter issues, verify that `scipfs_go_helper` is built correctly, that your IPFS daemon is operational, its API (`/ip4/127.0.0.1/tcp/5001` by default) is accessible, and its version meets the requirement.
- **Why this check?** This ensures that `scipfs` can reliably use IPFS commands and flags (like `ipfs routing findprovs --num-providers`) that might have changed or been introduced in specific versions.

### Client Implementation Status

**Migration Complete**: SciPFS has fully transitioned to using the `scipfs_go_helper` for all IPFS interactions. This includes operations such as adding files, pinning content, managing IPNS keys, publishing, resolving, and querying daemon information. The direct dependency on the Python `ipfshttpclient` library has been removed.

This unified approach aims to provide more consistent behavior and easier maintenance for IPFS communications.

---

## Understanding Content IDs (CIDs) and IPNS

### What is a CID?

A **Content ID (CID)** is a unique identifier for content stored on IPFS. It is derived from the content itself, meaning identical files have the same CID, regardless of who uploads them.

- CIDs are used to reference and retrieve files from the IPFS network.
- They ensure content is immutable and verifiable: if the content changes, the CID changes.

### What is IPNS?

**InterPlanetary Name System (IPNS)** is a system for creating mutable pointers to IPFS content. While a CID directly points to a specific, unchanging piece of content, an IPNS name is a public key hash that can be updated to point to new CIDs over time.

- Think of an IPNS name like a domain name that can always point to the latest version of your website, even as the website's content (and its CIDs) change.
- In SciPFS, IPNS is used to give each library a stable, human-friendly address that always points to its latest version (its latest manifest file).

### How CIDs and IPNS are Used in SciPFS

In SciPFS:
- Each file added to a library is uploaded to IPFS and assigned a unique CID.
- The library's **manifest** (a JSON file listing all files, their CIDs, and other metadata) is also stored on IPFS and has its own CID.
- When a library is created, SciPFS generates an **IPNS key pair**. The public key hash becomes the library's persistent **IPNS name** (e.g., `/ipns/k51q...`).
- The manifest's CID is then **published** to this IPNS name.
- Group members share and use the library's IPNS name to join and get updates. When the library owner adds files, the manifest changes (getting a new CID), and SciPFS automatically republishes this new manifest CID to the same IPNS name.

---

## Using SciPFS

### Initializing SciPFS

Before using SciPFS, initialize the configuration directory:

```bash
scipfs init
```

This creates a `.scipfs` directory in your home folder to store library manifests and configurations.

### Configuring Username

Before adding files to a library, it's good practice to set a username. This username will be recorded in the manifest alongside the files you add.

```bash
scipfs config set username <your_username>
```
- Example: `scipfs config set username alice`

### Creating a Library

To create a new library:

```bash
scipfs create <library_name>
```
- Replace `<library_name>` with a unique name for your library (e.g., `my-research-papers`).
- This command:
    1. Creates a local manifest file for the library.
    2. Generates an IPNS key pair. The key's name will be `<library_name>`.
    3. The public key hash becomes the library's persistent **IPNS name** (e.g., `/ipns/k51q...`).
    4. Adds the initial (empty) manifest to IPFS, getting its CID.
    5. Pins this manifest CID locally.
    6. Publishes the manifest CID to the newly generated IPNS name.
- The command will output the library's IPNS name and the initial manifest CID. **The IPNS name is what you share with others so they can join your library.**

Example:
```bash
scipfs create my-shared-docs
# Output might include:
# Successfully created library 'my-shared-docs'.
# IPNS Name (share this with others): /ipns/k51qkz0x...
# Initial Manifest CID: QmYp...
# Your local IPFS node is now publishing this library at the IPNS name.
# Note: IPNS propagation can take some time.
```

#### Customizing IPNS Record Lifetime

When you create a library, its IPNS name is published with a specific lifetime. This lifetime tells other IPFS nodes how long they should consider the record valid before trying to refresh it. By default, SciPFS uses a lifetime of "24h" (24 hours).

You can customize this lifetime using the `--ipns-lifetime` option when creating a library:

```bash
scipfs create <library_name> --ipns-lifetime <lifetime_value>
```
- Replace `<lifetime_value>` with a duration string like "48h" (48 hours), "7d" (7 days), "30d" (30 days), or even longer periods like "8760h" (approximately 1 year).
- This specified lifetime is stored in the library's manifest. When you later add files to this library and the manifest is republished, SciPFS will automatically reuse this same lifetime, ensuring consistent IPNS record persistence.

Example with custom lifetime:
```bash
scipfs create my-longterm-archive --ipns-lifetime 720h # 30 days
```

This gives you more control over how frequently your library's IPNS record needs to be refreshed by the network.

### Adding Files to a Library

To add a file to an existing library:

```bash
scipfs add <library_name> <file_path>
```
- `<library_name>`: The library name.
- `<file_path>`: Path to the file.
- The file is uploaded to IPFS and pinned locally. Its CID and your configured username are added to the library's manifest.
- If you are the **owner** (creator) of this library (i.e., your IPFS node holds the IPNS key for it, typically named after the library), SciPFS will automatically:
    1. Upload the updated manifest to IPFS (getting a new manifest CID).
    2. Pin the new manifest CID.
    3. Republish this new manifest CID to the library's IPNS name.
- If you are a member but not the owner, your local manifest will be updated, and a new manifest CID will be shown. You might need to coordinate with the library owner if you want your changes reflected in the primary IPNS record for the library.

Examples:
```bash
scipfs add my-shared-docs ./reports/report.pdf
# (Assumes 'my-shared-docs' was created by you or you have joined it)
```

### Listing Files in a Library

To list all files in a library:

```bash
scipfs list <library_name>
```

- Displays names, CIDs, and sizes of all files.

### Downloading Files from a Library

To download a file:

```bash
scipfs get <library_name> <file_name> <output_path> [--pin]
```

- `<library_name>`: Library name.
- `<file_name>`: File to download.
- `<output_path>`: Local save path. This can be a full file path, or a directory (in which case the file is saved with its original name into that directory).
- `--pin` (Optional): If specified, the downloaded file will also be pinned to your local IPFS node. Pinning a file tells your IPFS node to keep a persistent copy of it, making it available to you and others on the IPFS network even if the original provider goes offline. This is a good way to help ensure the durability and availability of files in a shared library.

To download all files from a library:

```bash
scipfs get <library_name> --all [<output_directory>] [--pin]
```

- If `<output_directory>` is provided, files are saved there.
- If `<output_directory>` is omitted, files are saved into a new directory named after the library in your current location.
- `--pin` (Optional): If specified, all downloaded files will also be pinned to your local IPFS node.

Examples:
```bash
# Download a single file
scipfs get my-research-papers report.pdf ./downloads/

# Download and pin a single file
scipfs get my-research-papers report.pdf ./downloads/report.pdf --pin

# Download all files to a specific directory
scipfs get my-research-papers --all ./all_my_papers/

# Download and pin all files to a default directory (./my-research-papers/)
scipfs get my-research-papers --all --pin
```

### Joining an Existing Library

To join a library shared by someone else:

```bash
scipfs join <ipns_name>
```
- `<ipns_name>`: The IPNS name of the library (e.g., `/ipns/k51q...`), shared by the library creator.
- This command:
    1. Resolves the IPNS name to find the CID of the library's latest manifest.
    2. Downloads the manifest from IPFS.
    3. Saves the manifest locally, allowing you to interact with the library (list files, get files, etc.).
- The library name will be derived from the manifest content.

Example:
```bash
scipfs join /ipns/k51qkz0x... # Use the actual IPNS name provided by the library creator
# Output might include:
# Successfully joined library 'someones-library' using IPNS name: /ipns/k51qkz0x...
# Manifest (CID: Qmabc...) saved to /home/user/.scipfs/someones-library_manifest.json
```
### Updating a Library (Getting Latest Changes)

If you have joined a library, or if you are the owner and changes were made from another machine, you can update your local copy of the library to the latest version published to its IPNS name:

```bash
scipfs update <library_name>
```
- `<library_name>`: The name of the library as it's known locally.
- This command will:
    1. Read the IPNS name stored in your local manifest for that library.
    2. Re-resolve this IPNS name to get the latest published manifest CID.
    3. Download and save the new manifest if it's different from your local one.

Example:
```bash
scipfs update my-shared-docs
```

### Viewing Library Info

To view details about a local library, including its manifest CID and IPNS name (if available):

```bash
scipfs info <library_name>
```

- Displays details about the library, including its manifest CID and IPNS name.

### Listing Local Libraries

To list all local libraries:

```bash
scipfs list-local
```

- Displays names and IPNS names of all local libraries.

### Listing Pinned Library Files

To list all files whose CIDs are pinned locally across all your SciPFS libraries:

```bash
scipfs list-pinned
```

- Displays names, CIDs, and sizes of files from your libraries that are currently pinned in your local IPFS node.
- Note: This checks the CIDs of files listed in your local library manifests against the CIDs reported as pinned by your IPFS node.

---

## Group Coordination (via IPNS)

### Sharing the Library (via IPNS Name)

When you create a library using `scipfs create <library_name>`, an IPNS key is generated, and the library is automatically published to an IPNS name derived from this key. This IPNS name (e.g., `/ipns/k51q...`) is shown in the output and is the primary identifier you should share with others so they can join and follow your library.

There is no separate `scipfs publish` command; publishing is an integral part of library creation and updates made by the library owner.

### How Library Updates Work

When the library owner adds files, the manifest changes (getting a new CID), and SciPFS automatically republishes this new manifest CID to the same IPNS name.

### Pinning Content for Availability

Pinning content to your local IPFS node helps ensure its availability to you and others on the network, even if the original provider goes offline. SciPFS provides several ways to pin content:

*   **Pin a specific CID:**
    ```bash
    scipfs pin cid <cid_string>
    ```
    -   `<cid_string>`: The Content ID to pin.

*   **Pin a local file (adds and pins):**
    This command will first add the file to IPFS (if not already added in the context of a library) and then pin its resulting CID.
    ```bash
    scipfs pin file <file_path>
    ```
    -   `<file_path>`: Path to the local file.

*   **Pin all files in a library:**
    This command iterates through all files in the specified library's manifest and pins each file's CID.
    ```bash
    scipfs pin library <library_name>
    ```
    -   `<library_name>`: The name of the library whose files you want to pin.

*   **Pin during download:**
    The `scipfs get` command also supports a `--pin` flag to pin files as they are downloaded:
    ```bash
    scipfs get <library_name> <file_name> --pin
    scipfs get <library_name> --all --pin
    ```

Pinning ensures that the data corresponding to the CID is kept in your IPFS node's local storage.

---

## Running Tests

To run the SciPFS test suite, use the following command:

```bash
pytest
```

This will run all the tests in the SciPFS project.

---

## Debugging Common Issues

### Can't Connect to IPFS Node

If you encounter issues connecting to your IPFS node, ensure:
1. Your IPFS daemon is running.
2. Your IPFS daemon is accessible via its default API port (5001).
3. Your IPFS daemon is not being blocked by any firewall or network policies.

### Files Not Found in Library

If files are not found in a library, ensure:
1. The file exists at the specified path.
2. The file is not corrupted.
3. The file is not being blocked by any network policies.

### Manifest Not Updating / Changes Not Visible

If changes are not visible in the library, ensure:
1. The library owner has added the changes to the library.
2. You have updated your local copy of the library.
3. The library owner has published the changes to its IPNS name.

---

## FAQ

### How do I get help if I encounter issues?

If you encounter issues, please check the [GitHub Issues](https://github.com/CameronBeebe/scipfs/issues) page for similar issues or open a new issue.

### How do I contribute to SciPFS?

If you are interested in contributing to SciPFS, please see the [Contributing](https://github.com/CameronBeebe/scipfs/blob/main/CONTRIBUTING.md) page for more information.

---

## Contributing

If you are interested in contributing to SciPFS, please see the [Contributing](https://github.com/CameronBeebe/scipfs/blob/main/CONTRIBUTING.md) page for more information.

