# ado_bulk_update

This is a project for performing bulk updates in ADO (Azure DevOps) using Python.

### Features
* changing one or more strings at once
* ability to change all occurrences of string(s) in the entire organization or specific projects and repositories
* dry run


## Installation

To install the required dependencies, run the following command:
```
pip install -r requirements.txt
```

[Az CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) is required for authentication

## Usage

* Authenticate with Azure DevOps using Az CLI:

    ```bash
    az login
    ```

* Adjust the settings.yaml file - at least change `organization_name` and change or remove `projects_and_repos`

* Run the script:

    ```bash
    python ado_bulk_update.py
    ```


## Settings

The `settings.yaml` file contains the following properties:

* `organization_name`: The name of the Azure DevOps organization.
* `projects_and_repos`: A list of projects and repositories to perform the bulk updates on. You can specify specific projects and repositories or leave it empty to perform the updates on the entire organization/project.
* `dry_run`: A boolean value indicating whether to perform a dry run or not. If set to `true`, the script will only simulate the updates without actually making any changes.