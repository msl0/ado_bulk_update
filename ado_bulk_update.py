"""
Copyright (c) 2024 Marcin Słowikowski
License: MIT
Description:
    The purpose of this script is to create bulk changes in an Azure DevOps
    repository. Script to search for a string in Azure DevOps repositories
    and replace it with another string. The script creates a new branch,
    updates the content of the file, and creates a pull request for the
    changes. The script uses the Azure DevOps Python SDK to interact with
    Azure DevOps services. The script reads the search string, the string to
    replace it with, and the repositories to search from a settings.yaml file.
    The script can be run in dry-run mode to simulate the changes without
    actually making them.
"""

from azure.identity import DefaultAzureCredential

from msrest.authentication import BasicTokenAuthentication
from azure.devops.connection import Connection
from azure.devops.exceptions import AzureDevOpsServiceError
from azure.devops.v7_0.search.models import CodeSearchRequest
from datetime import datetime
from urllib.parse import quote
import json
import sys
import textwrap
import yaml

from azure.devops.v7_0.git.models import (
    GitPush,
    Change,
    GitItem,
    ItemContent,
    GitRefUpdate,
    GitCommitRef,
    GitVersionDescriptor,
    GitPullRequestSearchCriteria,
)

with open("settings.yaml", "r") as file:
    settings = yaml.safe_load(file)

# Load settings from settings.yaml
strings_to_replace = settings.get("strings_to_replace")
projects_and_repos = settings.get("projects_and_repos", {None: None})
organization_name = settings.get("organization_name")
ado_base_url = settings.get("ado_base_url", "https://dev.azure.com/")
source_branch = settings.get("source_branch", "main")
dry_run = settings.get("dry_run", False)
new_branch = settings.get(
    "new_branch",
    f"bulk-update-{datetime.now().strftime('%Y%m%d')}"
)

organization_url = f"{ado_base_url}/{organization_name}"


def search_code(search_string, projects, repos):
    """
    Searches for code using the specified search string, projects,
        and repositories.

    Args:
        search_string (str): The search string to be used for code search.
        projects (list): A list of project names to filter the search results.
            Default is None.
        repos (list): A list of repository names to filter the search results.
            Default is None.

    Returns:
        CodeSearchResponse: The response object containing the code
            search results.
    """
    filters = {}

    if projects:
        filters['project'] = projects
    if repos:
        filters['repository'] = repos

    if not filters:
        filters = None

    search_client = connection.clients.get_search_client()
    search_request = CodeSearchRequest(
        search_text=search_string,
        top=1000,
        filters=filters,
        include_facets=False
    )

    try:
        response = search_client.fetch_code_search_results(
            request=search_request)
    except AzureDevOpsServiceError as e:
        print(textwrap.dedent(f"""
            An error occurred while fetching code search results
            Filters: {filters}
            Organization: {organization_name}
            Error message: {e}
        """))
        sys.exit(1)

    return response


def replace_string_in_file(
    project,
    repo_id,
    repo_name,
    file_path,
    old_string,
    new_string,
    new_branch
):
    """
    Replaces a specific string in a file
        and creates a pull request for the changes.

    Args:
        project (str): The name or ID of the project.
        repo_id (str): The ID of the repository.
        repo_name (str): The name of the repository.
        file_path (str): The path to the file in the repository.
        old_string (str): The string to be replaced.
        new_string (str): The new string to replace the old string.
        new_branch (str): The name of the new branch to create for the changes.

    Returns:
        None
    """

    git_client = connection.clients.get_git_client()

    last_commit = create_or_get_branch(
        project, repo_id, new_branch, git_client)

    item = git_client.get_item(
        project=project,
        repository_id=repo_id,
        path=file_path,
        include_content=True,
        version_descriptor=GitVersionDescriptor(
            version_type="branch", version=new_branch
        ),
    )
    existing_pr = git_client.get_pull_requests(
        repository_id=repo_id,
        project=project,
        search_criteria=GitPullRequestSearchCriteria(
            source_ref_name=f"refs/heads/{new_branch}",
            target_ref_name=f"refs/heads/{source_branch}",
            status="active",
        )
    )

    if len(existing_pr) != 0:
        pr_url = quote(f"https://dev.azure.com/{organization_name}/{
            project}/_git/{repo_name}/pullrequest/{existing_pr[0].pull_request_id}", safe=':/')

    if old_string not in item.content:

        if existing_pr:
            print(f"PR already exists: {pr_url}\n")
            return pr_url

    new_content = item.content.replace(old_string, new_string)

    update_file_content(project, repo_id, file_path,
                        new_branch, git_client, last_commit, new_content)

    if not existing_pr:
        pr = git_client.create_pull_request(
            git_pull_request_to_create={
                "source_ref_name": f"refs/heads/{new_branch}",
                "target_ref_name": f"refs/heads/{source_branch}",
                "title": "Bulk update",
            },
            repository_id=repo_id,
            project=project,
        )
        pr_url = quote(f"https://dev.azure.com/{organization_name}/{
            project}/_git/{repo_name}/pullrequest/{pr.pull_request_id}", safe=':/')
        print(f"PR created: {pr_url}\n")
    else:
        print(f"PR already exists: {pr_url}\n")

    return pr_url


def update_file_content(project, repo_id, file_path, new_branch,
                        git_client, last_commit, new_content):
    """
    Updates the content of a file in a Git repository.

    Args:
        project (str): The name or ID of the project.
        repo_id (str): The ID of the repository.
        file_path (str): The path of the file to be updated.
        new_branch (str): The name of the new branch to be created.
        git_client (GitClient): The Git client used to perform the update.
        last_commit (str): The ID of the last commit on the branch.
        new_content (str): The new content to be written to the file.

    Returns:
        None
    """
    change = Change(
        change_type="edit",
        item=GitItem(path=file_path),
        new_content=ItemContent(content=new_content, content_type="rawtext"),
    )

    push = GitPush(
        ref_updates=[
            GitRefUpdate(
                name=f"refs/heads/{new_branch}",
                old_object_id=last_commit)
        ],
        commits=[GitCommitRef(
            comment="Updated file content", changes=[change])],
    )

    git_client.create_push(push=push, project=project, repository_id=repo_id)


def create_or_get_branch(project, repo_id, new_branch, git_client):
    """
    Creates a new branch in a Git repository if it doesn't already exist,
    or retrieves the last commit ID of an existing branch.

    Args:
        project (str): The name or ID of the project.
        repo_id (str): The ID of the repository.
        new_branch (str): The name of the new branch to create or retrieve.
        git_client (GitClient): The Git client object.

    Returns:
        str: The commit ID of the last commit on the branch.
    """
    branches = git_client.get_branches(project=project, repository_id=repo_id)
    branch_exists = False
    for branch in branches:
        if branch.name == new_branch:
            branch_exists = True
            last_commit = branch.commit.commit_id
            break

    if not branch_exists:
        last_commit = git_client.get_branch(
            project=project, repository_id=repo_id, name=source_branch
        ).commit.commit_id
        create_branch = GitRefUpdate(
            is_locked=False,
            name=f"refs/heads/{new_branch}",
            old_object_id="0" * 40,
            new_object_id=last_commit,
        )
        git_client.update_refs(
            ref_updates=[create_branch], repository_id=repo_id, project=project
        )

    return last_commit


credential = DefaultAzureCredential()
token = credential.get_token("499b84ac-1321-427f-aa17-267ca6975798/.default")
credentials = BasicTokenAuthentication({"access_token": token.token})

connection = Connection(base_url=organization_url, creds=credentials)

pr_summary = []

for project, repos in projects_and_repos.items():
    for string in strings_to_replace:
        print(f"Searching for '{string['old']}'...\n")
        if project is None:
            response = search_code(string['old'], project, repos)
        else:
            response = search_code(string['old'], [project], repos)
        response_json = json.dumps(response.as_dict(), indent=4)

        if response.count == 0:
            if project is None:
                project = "all"
            if repos is None:
                repos = ["all"]
            print(
                f"No results found for the search string '{string['old']}' in "
                f"projects {project} and "
                f"repositories {', '.join(repos)}\n"
            )
            continue

        for result in response.results:
            print(
                f"Found '{string['old']}' in project '{result.project.name}' "
                f"and repository '{result.repository.name}' at '{result.path}'"
            )
            if not dry_run:
                print(f"Replacing '{string['old']}' with '{string['new']}'")
                pr_info = replace_string_in_file(
                    result.project.name,
                    result.repository.id,
                    result.repository.name,
                    result.path,
                    string['old'],
                    string['new'],
                    new_branch
                )
                pr_summary.append(pr_info)
if dry_run:
    print("Dry run. No changes made.")
else:
    pr_summary = list(set(pr_summary))
    print("PRs summary:\n" + "\n".join(pr_summary))
