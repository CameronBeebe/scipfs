# SciPFS

**SciPFS** is a command-line tool designed to help small groups and communities manage decentralized file libraries on the InterPlanetary File System (IPFS). It allows users to create, join, and manage libraries of files (such as PDFs, text files, or other types) that are shared and hosted across the group.

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
5. [Group Coordination (via IPNS)](#group-coordination-via-ipns)
   - [Sharing the Library (via IPNS Name)](#sharing-the-library-via-ipns-name)
   - [How Library Updates Work](#how-library-updates-work)
   - [Pinning CIDs for Availability](#pinning-cids-for-availability)
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

1. **Install SciPFS**:
   ```bash
   pip install scipfs
   ```

2. **Ensure IPFS is installed and running** (see [Setting Up IPFS](#setting-up-ipfs)).

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

### IPFS Version Compatibility

SciPFS uses the `ipfshttpclient` library to communicate with your IPFS daemon. This library typically supports a specific range of `go-ipfs` (the IPFS daemon) versions.

-   **You might see a `VersionMismatch` warning** when `scipfs` commands are run if your IPFS daemon version is outside the range officially supported by the `ipfshttpclient` version bundled with SciPFS (currently `ipfshttpclient==0.8.0a2`, which ideally works with `go-ipfs` versions `0.5.0` to `<0.9.0`).
-   For example, if you are running an older IPFS daemon (e.g., `0.34.1`), you will likely see this warning.
-   While basic functionality might still work (as demonstrated by the project's tests with older daemons), using a mismatched version can lead to unexpected behavior or errors with certain features.
-   **Recommendation**: For best results and stability, try to use an IPFS daemon version that is within the supported range of the `ipfshttpclient`. You can check the `ipfshttpclient` documentation for its currently supported `go-ipfs` versions. Alternatively, future versions of SciPFS may update this dependency or offer guidance for specific daemon versions.

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
```

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
scipfs get <library_name> <file_name> <output_path>
```

- `<library_name>`: Library name.
- `<file_name>`: File to download.
- `<output_path>`: Local save path.

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

Example:
```bash
scipfs info my-shared-docs
```

### Listing Local Libraries

To see all the SciPFS libraries you have created or joined that have local manifests:

```bash
scipfs list-local
```

---

## Group Coordination (via IPNS)

SciPFS uses IPNS to simplify sharing and updating libraries.

### Sharing the Library (via IPNS Name)

1.  **Creator**: When you create a library using `scipfs create <library_name>`, the command outputs an **IPNS name** (e.g., `/ipns/k51q...`).
2.  **Share this IPNS name** with your group members. This is the stable address for your library.
3.  **Members**: Use `scipfs join <ipns_name>` (using the IPNS name you provided) to get a local copy of the library manifest and start interacting with the library.

### How Library Updates Work

-   **For the Library Owner (Creator)**:
    -   When you add files using `scipfs add <library_name> <file_path>`, SciPFS automatically updates the local manifest, uploads the new manifest to IPFS (getting a new CID), and then **republishes this new manifest CID to the library's original IPNS name**.
    -   Your IPFS node handles the IPNS update because it holds the private key for that IPNS name.

-   **For Library Members (Non-Owners)**:
    -   When you add files using `scipfs add <library_name> <file_path>`, your **local manifest is updated**, and a new manifest CID is generated and shown. This change is only on your machine.
    -   To make these additions visible to everyone via the library's main IPNS name, the library owner would typically need to add those same files (or obtain your new manifest CID and manually publish it, though `scipfs` doesn't automate this for non-owners). For most collaborative workflows, it's common for one person (the owner/maintainer) to be responsible for publishing updates to the primary IPNS name.

-   **Getting Updates (All Members, Including Owner on Different Machines)**:
    -   Anyone who has joined the library can get the latest changes by running:
        ```bash
        scipfs update <library_name>
        ```
    -   This command fetches the latest manifest CID published to the library's IPNS name and updates the local manifest file.
    -   **Note**: IPNS propagation across the IPFS network can take some time (minutes to hours in some cases). If a library owner publishes an update, other members might not see it immediately when they run `scipfs update`.

### Pinning CIDs for Availability

- Encourage all members to pin manifest and file CIDs for redundancy. SciPFS automatically pins manifests and files when they are created, added, or joined/updated.

---

## Running Tests

The `scipfs` repository includes a basic integration test script. To run the tests:

1.  **Prerequisites**:
    *   Ensure your IPFS daemon is running.
    *   Ensure `scipfs` is installed and available in your PATH (e.g., if you installed it from source using `pip install .` in the project directory).
2.  **Execute the test script**:
    Navigate to the root directory of the `scipfs` project in your terminal and run:
    ```bash
    bash tests/run_basic_tests.sh
    ```
    The script will perform various operations like creating libraries, adding files, and getting files, and then clean up after itself.

---

## Debugging Common Issues

### Can't Connect to IPFS Node

**Symptoms**:
- Errors like "Failed to connect to IPFS node" or "Could not connect to IPFS node at /ip4/127.0.0.1/tcp/5001".

**Solutions**:
1. Ensure the daemon is running:
   ```bash
   ipfs daemon
   ```
2. Verify the node address. SciPFS uses `/ip4/127.0.0.1/tcp/5001` by default. Adjust if needed (future feature).

### Files Not Found in Library

**Symptoms**:
- Missing files when using `scipfs list <library_name>`.
- "File not found in library" error when using `scipfs get <library_name> <file_name>`.

**Solutions**:
1.  Ensure your local manifest is up-to-date by running:
    ```bash
    scipfs update <library_name>
    ```
2.  Allow some time for IPNS records to propagate if the library was just updated by the owner.
3.  Verify the file is indeed in the manifest after updating:
    ```bash
    scipfs list <library_name>
    ```
4.  If you are the library owner, ensure you successfully added the file and that the `scipfs add` command completed without errors.

### Manifest Not Updating / Changes Not Visible

**Symptoms**:
- After the library owner adds files, other members (or the owner on a different machine) run `scipfs update <library_name>` but still see the old version of the library.
- `scipfs info <library_name>` shows an old manifest CID.

**Solutions**:
1.  **For Library Owner**:
    *   Ensure the `scipfs add` command completed successfully and a new manifest CID was generated and published. Check for any error messages.
    *   Your IPFS daemon must be running and connected to the network to publish IPNS updates.
2.  **For All Members**:
    *   Run `scipfs update <library_name>` again after some time. IPNS propagation is not instantaneous and can take minutes or longer.
    *   Verify the library's IPNS name being used is correct.
3.  Check your IPFS daemon's logs for any issues related to IPNS resolution or publishing.

---

## FAQ

**Q: Do all members need their own IPFS daemon?**  
A: Yes, each needs a local daemon to interact with IPFS.

**Q: How do I keep files available if members are offline?**  
A: Multiple members should pin the same CIDs for higher availability.

**Q: Can I use a remote IPFS node?**  
A: Currently, SciPFS supports only local nodes. Remote support may come later.

---

## Contributing

Details on how to contribute to SciPFS will be added here in the future. For now, please use the GitHub issue tracker for bug reports or feature suggestions.

---

This documentation provides clear instructions for setting up IPFS, managing CIDs, coordinating with a group, and debugging common issues. Happy sharing!