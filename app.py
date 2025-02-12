import sys
import os
import json
import logging
import datetime
import boto3
from github_api_toolkit import github_graphql_interface, get_token_as_installation

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Clear any existing handlers
for handler in logger.handlers:
    logger.removeHandler(handler)

# Add stdout handler
stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
)
logger.addHandler(stdout_handler)

def find_keywords_in_file(file, keywords_list):
    """Find keywords in a file

    Args:
        file (str): File contents that you are interested in searching
        keywords_list (list): List of keywords that you want to search through the file

    Returns:
        list: List of keywords that were found in the file
    """    
    keywords = []
    if file is not None:
        for keyword in keywords_list:
            if (keyword.lower() in file.lower()) and (keyword.lower() not in keywords):
                keywords.append(keyword)
        return keywords
    return []    

def get_repository_technologies(ql, org, batch_size=5):
    """Gets technology information for all repositories in an organization"""

    query = """
    query($org: String!, $limit: Int!, $cursor: String) {
      organization(login: $org) {
        repositories(first: $limit, after: $cursor) {
          pageInfo {
            hasNextPage
            endCursor
          }
          nodes {
            name
            url
            visibility
            isArchived
            defaultBranchRef {
              target {
                ... on Commit {
                  committedDate
                  history(first: 1) {
                    nodes {
                      committedDate
                    }
                  }
                }
              }
            }
            languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
              edges {
                size
                node {
                  name
                  color
                }
              }
              totalSize
            }
            object(expression: "HEAD:") {
          ... on Tree {
            entries {
              name
              type
              object {
                ... on Blob {
                    text
                }
                ... on Tree {
                    entries {
                        name
                    }
                }
              }
            }
          }
        }
          }
        }
      }
    }
    """

    has_next_page = True
    cursor = None
    all_repos = []
    # test CI

    # Statistics tracking
    total_repos = 0
    private_repos = 0
    public_repos = 0
    internal_repos = 0
    archived_repos = 0
    archived_private = 0
    archived_public = 0
    archived_internal = 0
    language_stats = {}
    archived_language_stats = {}  # New dictionary for archived repos
                    
    while has_next_page:
        variables = {"org": org, "limit": batch_size, "cursor": cursor}
        fail_count = 0

        while fail_count < 5:
            result = ql.make_ql_request(query, variables)

            if not result.ok:
                logger.error("GraphQL query failed: {}", result.status_code)
                fail_count += 1
                logger.info('RETRYING...')
            else:
                break
        if fail_count == 5:
            break
                

        data = result.json()
        if "errors" in data:
            logger.error("GraphQL query returned errors: {}", data['errors'])
            break

        repos = data["data"]["organization"]["repositories"]["nodes"]

        for repo in repos:
            try:
                # Count repository visibility
                total_repos += 1
                is_archived = repo.get("isArchived", False)
                
                if is_archived:
                    archived_repos += 1
                    if repo["visibility"] == "PRIVATE":
                        archived_private += 1
                    elif repo["visibility"] == "PUBLIC":
                        archived_public += 1
                    elif repo["visibility"] == "INTERNAL":
                        archived_internal += 1
                
                if repo["visibility"] == "PRIVATE":
                    private_repos += 1
                elif repo["visibility"] == "PUBLIC":
                    public_repos += 1
                elif repo["visibility"] == "INTERNAL":
                    internal_repos += 1

                # Get last commit date
                last_commit_date = None
                if repo.get("defaultBranchRef") and repo["defaultBranchRef"].get("target"):
                    last_commit_date = repo["defaultBranchRef"]["target"].get("committedDate")

                # Process languages
                languages = []
                IAC = []
                if repo["languages"]["edges"]:
                    total_size = repo["languages"]["totalSize"]
                    for edge in repo["languages"]["edges"]:
                        lang_name = edge["node"]["name"]
                        if lang_name == "HCL":
                            IAC.append("Terraform")
                        if lang_name == "Dockerfile":
                            IAC.append("Docker")
                        percentage = (edge["size"] / total_size) * 100

                        # Choose which statistics dictionary to update based on archive status
                        stats_dict = archived_language_stats if is_archived else language_stats
                        
                        # Update language statistics
                        if lang_name not in stats_dict:
                            stats_dict[lang_name] = {
                                "repo_count": 0,
                                "average_percentage": 0,
                                "total_size": 0,
                            }
                        stats_dict[lang_name]["repo_count"] += 1
                        stats_dict[lang_name]["average_percentage"] += percentage
                        stats_dict[lang_name]["total_size"] += edge["size"]

                        languages.append(
                            {
                                "name": lang_name,
                                "size": edge["size"],
                                "percentage": percentage,
                            }
                        )
                
                documentation_list = ["Confluence", "MKDocs", "Sphinx", "ReadTheDocs"]
                cloud_services_list = ["AWS", "Azure", "GCP"]
                frameworks_list = ["React", "Angular", "Vue", "Django", "Streamlit", "Flask", "Spring", "Hibernate", "Express", "Next.js", "Play", "Akka", "Lagom"]
                ci_cd_list = ["Jenkins", "GitHub Actions", "GitLab CI", "CircleCI", "Travis CI", "Azure DevOps", "Concourse"]
                ci_cd = []
                docs = []
                cloud = []
                if repo["object"] is not None:
                    # json.dump(repo["object"]["entries"], file, indent=4)
                    # repo["object"]["entries"] is a LIST of dictionaries
                    # Get README content
                    readme_content = pyproject_content = package_json_content = None
                    if repo["object"]["entries"]:
                        for entry in repo["object"]["entries"]:
                            if entry["name"].lower() == "readme.md":
                                readme_content = entry["object"]["text"]
                            if entry["name"].lower() == "pyproject.toml":
                                pyproject_content = entry["object"]["text"]
                    
                    frameworks_pyproject = find_keywords_in_file(pyproject_content, frameworks_list)
                    frameworks_package_json = find_keywords_in_file(package_json_content, frameworks_list)
                    frameworks = frameworks_pyproject + frameworks_package_json
                    # Check if "confluence" is present in README
                    if readme_content is not None:
                        for doc, cl in zip(documentation_list, cloud_services_list):
                            if doc.lower() in readme_content.lower():
                                docs.append(doc)
                            if cl.lower() in readme_content.lower():
                                cloud.append(cl)
                    
                    # Extremely hardcoded, will need to write a general tree traversal to find
                    # things in all directories
                    if repo["object"]["entries"]:
                        for entry in repo["object"]["entries"]:
                            if entry["name"] == ".github":
                                if entry["object"]["entries"]:
                                    for gh_entry in entry["object"]["entries"]:
                                        if gh_entry["name"] == "workflows":
                                            ci_cd.append("GitHub Actions")
                                            break
                            if entry["name"] == "ci":
                                if entry["object"]["entries"]:
                                    for ci_entry in entry["object"]["entries"]:
                                        if "pipeline.yml" in ci_entry["name"]:
                                            ci_cd.append("Concourse")
                                            break

                repo_info = {
                    "name": repo["name"],
                    "url": repo["url"],
                    "visibility": repo["visibility"],
                    "is_archived": is_archived,
                    "last_commit": last_commit_date,
                    "technologies": {"languages": languages, "IAC": IAC, "docs": docs, "cloud": cloud, "frameworks": frameworks, "ci_cd": ci_cd},
                }

                all_repos.append(repo_info)

            except Exception as e:
                logger.error(
                    "Error processing repository {}: {}".format(
                        repo.get("name", "unknown"), str(e)
                    )
                )

        logger.info("Processed {} repositories".format(len(all_repos)))

        page_info = data["data"]["organization"]["repositories"]["pageInfo"]
        has_next_page = page_info["hasNextPage"]
        cursor = page_info["endCursor"]

    # Calculate language averages for non-archived repos
    language_averages = {}
    for lang, stats in language_stats.items():
        language_averages[lang] = {
            "repo_count": stats["repo_count"],
            "average_percentage": round(
                stats["average_percentage"] / stats["repo_count"], 3
            ),
            "total_size": stats["total_size"],
        }

    # Calculate language averages for archived repos
    archived_language_averages = {}
    for lang, stats in archived_language_stats.items():
        archived_language_averages[lang] = {
            "repo_count": stats["repo_count"],
            "average_percentage": round(
                stats["average_percentage"] / stats["repo_count"], 3
            ),
            "total_size": stats["total_size"],
        }

    # Create final output
    output = {
        "repositories": all_repos,
        "stats_unarchived": {
            "total": total_repos - archived_repos,
            "private": private_repos - archived_private,
            "public": public_repos - archived_public,
            "internal": internal_repos - archived_internal,
            "active_last_month": sum(
                1 for repo in all_repos 
                if repo["last_commit"] and not repo["is_archived"] and
                (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(repo["last_commit"].replace("Z", "+00:00"))).days <= 30
            ),
            "active_last_3months": sum(
                1 for repo in all_repos 
                if repo["last_commit"] and not repo["is_archived"] and
                (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(repo["last_commit"].replace("Z", "+00:00"))).days <= 90
            ),
            "active_last_6months": sum(
                1 for repo in all_repos 
                if repo["last_commit"] and not repo["is_archived"] and
                (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(repo["last_commit"].replace("Z", "+00:00"))).days <= 180
            )
        },
        "stats_archived": {
            "total": archived_repos,
            "private": archived_private,
            "public": archived_public,
            "internal": archived_internal,
            "active_last_month": sum(
                1 for repo in all_repos 
                if repo["last_commit"] and repo["is_archived"] and
                (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(repo["last_commit"].replace("Z", "+00:00"))).days <= 30
            ),
            "active_last_3months": sum(
                1 for repo in all_repos 
                if repo["last_commit"] and repo["is_archived"] and
                (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(repo["last_commit"].replace("Z", "+00:00"))).days <= 90
            ),
            "active_last_6months": sum(
                1 for repo in all_repos 
                if repo["last_commit"] and repo["is_archived"] and
                (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(repo["last_commit"].replace("Z", "+00:00"))).days <= 180
            )
        },
        "language_statistics_unarchived": language_averages,
        "language_statistics_archived": archived_language_averages,
        "metadata": {
            "last_updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        },
    }

    # Write everything to file at once
    with open("repositories.json", "w") as file:
        json.dump(output, file, indent=2)
        file.write("\n")

    return all_repos


def handler(event, context):
    """Main function to run the GitHub technology audit"""
    try:
        # Configuration
        org = os.getenv("GITHUB_ORG")
        client_id = os.getenv("GITHUB_APP_CLIENT_ID")
        secret_name = os.getenv("AWS_SECRET_NAME")
        secret_region = os.getenv("AWS_DEFAULT_REGION")
        bucket_name = os.getenv("SOURCE_BUCKET")

        logger.info("Starting GitHub technology audit")

        # Set up AWS session
        session = boto3.Session()
        secret_manager = session.client("secretsmanager", region_name=secret_region)

        # Get GitHub token
        logger.info("Getting GitHub token from AWS Secrets Manager")
        secret = secret_manager.get_secret_value(SecretId=secret_name)["SecretString"]

        token = get_token_as_installation(org, secret, client_id)
        if not token:
            logger.error('Error getting GitHub token')
            return {"statusCode": 500, "body": json.dumps("Failed to get GitHub token")}

        logger.info("Successfully obtained GitHub token")
        ql = github_graphql_interface(str(token[0]))

        # Get repository technology information
        repos = get_repository_technologies(ql, org)
        
        s3 = boto3.client('s3')
        s3.upload_file('repositories.json', bucket_name, 'repositories.json')
        # Print or save results
        output = {
            "message": "Successfully analyzed repository technologies",
            "repository_count": len(repos),
            "repositories": repos,
        }

    except Exception as e:
        logger.error("Execution failed: %s", str(e))

# Uncomment the following line to run the function locally
"""
if __name__ == "__main__":
    handler(None, None)
"""