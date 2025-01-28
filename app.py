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

BATCH_SIZE = os.getenv("BATCH_SIZE", 20)


def check_infrastructure_files(entries):
    """Check repository for infrastructure as code indicators"""
    iac = []
    if entries is None:
        return iac

    for entry in entries:
        # Check for Terraform
        if entry["name"].endswith(".tf") or entry["name"] == "terraform":
            iac.append("Terraform")
        # Check for CloudFormation
        elif entry["name"].endswith((".yaml", ".yml", ".json")):
            if entry.get("object") and entry["object"].get("text"):
                content = entry["object"]["text"].lower()
                if "awstemplate" in content or "cloudformation" in content:
                    iac.append("CloudFormation")
        # Check for Kubernetes
        elif entry["name"].endswith((".yaml", ".yml")):
            if entry.get("object") and entry["object"].get("text"):
                content = entry["object"]["text"].lower()
                if "kind: deployment" in content or "kind: service" in content:
                    iac.append("Kubernetes")
        # Check for Ansible
        elif entry["name"] == "ansible" or (
            entry["name"].endswith(".yml") and "playbook" in entry["name"].lower()
        ):
            iac.append("Ansible")

    return list(set(iac))


def check_cloud_providers(entries, readme_content=None):
    """Check repository for cloud provider indicators"""
    cloud = []

    if entries is None:
        return cloud

    for entry in entries:
        # AWS indicators
        if entry["name"] in ["template.yaml", "cloudformation", "cdk.json"]:
            cloud.append("AWS")
        elif entry["name"].endswith(".tf"):
            if entry.get("object") and entry["object"].get("text"):
                if 'provider "aws"' in entry["object"]["text"].lower():
                    cloud.append("AWS")

        # GCP indicators
        elif entry["name"] == "gcp" or entry["name"].endswith(".bicep"):
            cloud.append("GCP")
        elif entry["name"].endswith(".tf"):
            if entry.get("object") and entry["object"].get("text"):
                if 'provider "google"' in entry["object"]["text"].lower():
                    cloud.append("GCP")

        # Azure indicators
        elif entry["name"].endswith((".json", ".bicep")):
            if entry.get("object") and entry["object"].get("text"):
                content = entry["object"]["text"].lower()
                if "microsoft.azure" in content or ".azure." in content:
                    cloud.append("Azure")

    # Check README content if provided
    if readme_content:
        readme_lower = readme_content.lower()
        if any(
            term in readme_lower
            for term in ["aws", "amazon web services", "cloudformation", "boto3"]
        ):
            cloud.append("AWS")
        if any(
            term in readme_lower
            for term in ["gcp", "google cloud", "gcloud", "google.cloud"]
        ):
            cloud.append("GCP")
        if any(
            term in readme_lower for term in ["azure", "microsoft azure", "azure cli"]
        ):
            cloud.append("Azure")

    return list(set(cloud))


def check_ci_cd(entries):
    """Check repository for CI/CD pipeline indicators"""
    ci_cd = []

    if entries is None:
        return ci_cd

    for entry in entries:
        # GitHub Actions
        if entry["name"] == ".github":
            if entry.get("object") and entry["object"].get("entries"):
                for gh_entry in entry["object"]["entries"]:
                    if gh_entry["name"] == "workflows":
                        ci_cd.append("GitHub Actions")
                        break

        # Jenkins
        elif entry["name"] == "Jenkinsfile" or entry["name"] == "jenkins":
            ci_cd.append("Jenkins")

        # CircleCI
        elif entry["name"] == ".circleci":
            ci_cd.append("CircleCI")

        # Travis
        elif entry["name"] == ".travis.yml":
            ci_cd.append("Travis CI")

        # Concourse
        elif entry["name"] == "ci":
            if entry.get("object") and entry["object"].get("entries"):
                for ci_entry in entry["object"]["entries"]:
                    if "pipeline.yml" in ci_entry["name"]:
                        ci_cd.append("Concourse")
                        break

    return list(set(ci_cd))


def check_documentation(entries):
    """Check repository for documentation indicators"""
    docs = []

    if entries is None:
        return docs

    doc_directories = ["docs", ".docs", "documentation", "guides"]
    doc_tools = {
        "_config.yml": "Jekyll",
        "conf.py": "Sphinx",
        "mkdocs.yml": "MkDocs",
        "docusaurus.config.js": "Docusaurus",
    }

    for entry in entries:
        # Check for documentation directories
        if entry["name"] in doc_directories:
            docs.append("Documentation Directory")

        # Check for specific documentation tools
        if entry["name"] in doc_tools:
            docs.append(doc_tools[entry["name"]])

        # Check for multiple markdown files (beyond just README)
        if entry["type"] == "Tree" and entry.get("object"):
            md_count = sum(
                1
                for e in entry["object"]["entries"]
                if e["name"].endswith(".md") and e["name"].lower() != "readme.md"
            )
            if md_count > 0:
                docs.append("Markdown Documentation")

    return list(set(docs))


def check_testing(entries):
    """Check repository for testing framework indicators"""
    tests = []

    if entries is None:
        return tests

    test_directories = ["tests", "test", "spec"]

    for entry in entries:
        # Check for test directories
        if entry["name"] in test_directories:
            tests.append("Test Directory")

        # Check for test files
        if entry["name"].startswith("test_") or entry["name"].endswith("_test.py"):
            tests.append("Test Files")

        # Check package files for testing frameworks
        if entry["name"] in ["package.json", "requirements.txt", "setup.py"]:
            if entry.get("object") and entry["object"].get("text"):
                content = entry["object"]["text"].lower()
                if any(
                    framework in content
                    for framework in [
                        "pytest",
                        "unittest",
                        "jest",
                        "mocha",
                        "cypress",
                        "junit",
                    ]
                ):
                    tests.append("Testing Framework")

    return list(set(tests))


def check_python_dependencies(entries, recursive=True):
    """Check repository for Python package dependencies, optionally checking subdirectories"""
    dependencies = {
        "requirements": [],
        "poetry": {"dependencies": [], "dev_dependencies": []},
        "authors": [],
        "package_manager": [],
    }

    if entries is None:
        return dependencies

    def process_entries(entries_list):
        for entry in entries_list:
            # Check requirements.txt files
            if entry["name"].endswith(".txt"):
                if entry.get("object") and entry["object"].get("text"):
                    content = entry["object"]["text"]
                    # Look for package requirements
                    for line in content.splitlines():
                        line = line.strip()
                        if line and not line.startswith("#"):
                            if "==" in line:
                                package = line.split("==")[0].strip()
                                dependencies["requirements"].append(package)
                            elif ">=" in line:
                                package = line.split(">=")[0].strip()
                                dependencies["requirements"].append(package)
                    dependencies["package_manager"].append("pip")

            # Check pyproject.toml
            elif entry["name"] == "pyproject.toml":
                if entry.get("object") and entry["object"].get("text"):
                    content = entry["object"]["text"]
                    try:
                        try:
                            import toml

                            pyproject = toml.loads(content)
                            # If toml is available, use it to parse
                            if "tool" in pyproject and "poetry" in pyproject["tool"]:
                                poetry = pyproject["tool"]["poetry"]

                                # Get main dependencies
                                if "dependencies" in poetry:
                                    dependencies["poetry"]["dependencies"] = list(
                                        poetry["dependencies"].keys()
                                    )

                                # Get dev dependencies
                                if "group" in poetry and "dev" in poetry["group"]:
                                    if "dependencies" in poetry["group"]["dev"]:
                                        dependencies["poetry"]["dev_dependencies"] = (
                                            list(
                                                poetry["group"]["dev"][
                                                    "dependencies"
                                                ].keys()
                                            )
                                        )

                                # Get authors
                                if "authors" in poetry:
                                    dependencies["authors"] = poetry["authors"]

                                dependencies["package_manager"].append("poetry")
                        except ImportError:
                            logger.warning(
                                "toml package not available, falling back to basic parsing"
                            )
                            # Basic parsing for poetry dependencies
                            lines = content.splitlines()
                            in_dependencies = False
                            in_dev_dependencies = False
                            for line in lines:
                                if "[tool.poetry.dependencies]" in line:
                                    in_dependencies = True
                                    in_dev_dependencies = False
                                    continue
                                elif "[tool.poetry.group.dev.dependencies]" in line:
                                    in_dependencies = False
                                    in_dev_dependencies = True
                                    continue
                                elif line.startswith("["):
                                    in_dependencies = False
                                    in_dev_dependencies = False
                                    continue

                                if in_dependencies and "=" in line:
                                    package = line.split("=")[0].strip()
                                    if package and package != "python":
                                        dependencies["poetry"]["dependencies"].append(
                                            package
                                        )
                                elif in_dev_dependencies and "=" in line:
                                    package = line.split("=")[0].strip()
                                    if package:
                                        dependencies["poetry"][
                                            "dev_dependencies"
                                        ].append(package)

                            dependencies["package_manager"].append("poetry")
                    except Exception as e:
                        logger.error(f"Failed to parse pyproject.toml: {str(e)}")
                        continue

            # Check setup.py
            elif entry["name"] == "setup.py":
                if entry.get("object") and entry["object"].get("text"):
                    content = entry["object"]["text"].lower()
                    if "install_requires" in content:
                        dependencies["package_manager"].append("setuptools")

            # Check Pipfile
            elif entry["name"] == "Pipfile":
                if entry.get("object") and entry["object"].get("text"):
                    dependencies["package_manager"].append("pipenv")

            # Check conda environment.yml
            elif entry["name"] in ["environment.yml", "environment.yaml"]:
                if entry.get("object") and entry["object"].get("text"):
                    dependencies["package_manager"].append("conda")

            # Recursively check subdirectories
            elif (
                recursive
                and entry["type"] == "Tree"
                and entry.get("object")
                and entry["object"].get("entries")
            ):
                process_entries(entry["object"]["entries"])

    # Start processing from root
    process_entries(entries)

    # Remove duplicates
    dependencies["requirements"] = list(set(dependencies["requirements"]))
    dependencies["package_manager"] = list(set(dependencies["package_manager"]))

    return dependencies


def check_javascript_dependencies(entries, recursive=True):
    """Check repository for JavaScript package dependencies and frameworks"""
    dependencies = {
        "dependencies": [],
        "dev_dependencies": [],
        "frameworks": [],
        "package_manager": [],
    }

    if entries is None:
        return dependencies

    framework_indicators = {
        "react": ["react", "react-dom", "create-react-app", "next.js", "gatsby"],
        "vue": ["vue", "vuex", "vue-router", "@vue/cli", "nuxt"],
        "angular": ["@angular/core", "@angular/cli", "angular"],
        "svelte": ["svelte", "svelte-kit"],
        "express": ["express"],
        "nest": ["@nestjs/core"],
        "jquery": ["jquery"],
    }

    for entry in entries:
        # Check package.json
        if entry["name"] == "package.json":
            if entry.get("object") and entry["object"].get("text"):
                try:
                    package_json = json.loads(entry["object"]["text"])

                    # Get dependencies
                    if "dependencies" in package_json:
                        new_deps = list(package_json["dependencies"].keys())
                        dependencies["dependencies"].extend(new_deps)
                        # Check for frameworks in dependencies
                        for dep in package_json["dependencies"].keys():
                            for framework, indicators in framework_indicators.items():
                                if any(
                                    indicator in dep.lower() for indicator in indicators
                                ):
                                    dependencies["frameworks"].append(framework)

                    # Get dev dependencies
                    if "devDependencies" in package_json:
                        new_dev_deps = list(package_json["devDependencies"].keys())
                        dependencies["dev_dependencies"].extend(new_dev_deps)
                        # Check for frameworks in devDependencies
                        for dep in package_json["devDependencies"].keys():
                            for framework, indicators in framework_indicators.items():
                                if any(
                                    indicator in dep.lower() for indicator in indicators
                                ):
                                    dependencies["frameworks"].append(framework)

                    dependencies["package_manager"].append("npm")

                    # Check for specific package managers
                    if "packageManager" in package_json:
                        if "yarn" in package_json["packageManager"]:
                            dependencies["package_manager"].append("yarn")
                        elif "pnpm" in package_json["packageManager"]:
                            dependencies["package_manager"].append("pnpm")
                except Exception as e:
                    logger.error(f"Failed to parse package.json: {str(e)}")
                    continue

        # Check for yarn.lock
        elif entry["name"] == "yarn.lock":
            dependencies["package_manager"].append("yarn")

        # Check for pnpm-lock.yaml
        elif entry["name"] == "pnpm-lock.yaml":
            dependencies["package_manager"].append("pnpm")

        # Check for framework-specific files
        elif entry["name"] == "angular.json":
            dependencies["frameworks"].append("angular")
        elif entry["name"] == "vue.config.js":
            dependencies["frameworks"].append("vue")
        elif entry["name"] == "svelte.config.js":
            dependencies["frameworks"].append("svelte")
        elif entry["name"] == "next.config.js":
            dependencies["frameworks"].append("react")
            dependencies["frameworks"].append("next.js")
        elif entry["name"] == "gatsby-config.js":
            dependencies["frameworks"].append("react")
            dependencies["frameworks"].append("gatsby")

    # Remove duplicates
    dependencies["dependencies"] = list(set(dependencies["dependencies"]))
    dependencies["dev_dependencies"] = list(set(dependencies["dev_dependencies"]))
    dependencies["frameworks"] = list(set(dependencies["frameworks"]))
    dependencies["package_manager"] = list(set(dependencies["package_manager"]))

    return dependencies


def get_repository_technologies(ql, org, batch_size=BATCH_SIZE):
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
            homepageUrl
            visibility
            isArchived
            defaultBranchRef {
              target {
                ... on Commit {
                  committedDate
                  history(first: 1) {
                    nodes {
                      committedDate
                      author {
                        name
                        email
                      }
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
                        type
                        object {
                          ... on Blob {
                            text
                          }
                          ... on Tree {
                            entries {
                              name
                              type
                              object {
                                ... on Blob {
                                  text
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
        result = ql.make_ql_request(query, variables)

        if not result.ok:
            logger.error("GraphQL query failed: {}", result.status_code)
            break

        data = result.json()
        if "errors" in data:
            logger.error("GraphQL query returned errors: {}", data["errors"])
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
                if repo.get("defaultBranchRef") and repo["defaultBranchRef"].get(
                    "target"
                ):
                    last_commit_date = repo["defaultBranchRef"]["target"].get(
                        "committedDate"
                    )

                # Process languages
                languages = []
                IAC = []
                has_python = False
                has_javascript = False
                if repo["languages"]["edges"]:
                    total_size = repo["languages"]["totalSize"]
                    for edge in repo["languages"]["edges"]:
                        lang_name = edge["node"]["name"]
                        if lang_name == "Python":
                            has_python = True
                        if lang_name in ["JavaScript", "TypeScript"]:
                            has_javascript = True
                        if lang_name == "HCL":
                            IAC.append("Terraform")
                        if lang_name == "Dockerfile":
                            IAC.append("Docker")
                        percentage = (edge["size"] / total_size) * 100

                        # Choose which statistics dictionary to update based on archive status
                        stats_dict = (
                            archived_language_stats if is_archived else language_stats
                        )

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

                # Add dependencies checks
                python_deps = {}
                if has_python:
                    python_deps = check_python_dependencies(
                        repo["object"]["entries"] if repo["object"] else None
                    )

                javascript_deps = {}
                if has_javascript:
                    javascript_deps = check_javascript_dependencies(
                        repo["object"]["entries"] if repo["object"] else None
                    )

                documentation_list = ["Confluence", "MKDocs", "Sphinx", "ReadTheDocs"]
                cloud_services_list = ["AWS", "Azure", "GCP"]
                frameworks_list = [
                    "React",
                    "Angular",
                    "Vue",
                    "Django",
                    "Streamlit",
                    "Flask",
                    "Spring",
                    "Hibernate",
                    "Express",
                    "Next.js",
                    "Play",
                    "Akka",
                    "Lagom",
                ]
                ci_cd_list = [
                    "Jenkins",
                    "GitHub Actions",
                    "GitLab CI",
                    "CircleCI",
                    "Travis CI",
                    "Azure DevOps",
                    "Concourse",
                ]
                ci_cd = []
                frameworks = []
                docs = []
                cloud = []
                if repo["object"] is not None:
                    # json.dump(repo["object"]["entries"], file, indent=4)
                    # repo["object"]["entries"] is a LIST of dictionaries
                    # Get README content
                    readme_content = None
                    makefile_content = None
                    if repo["object"]["entries"]:
                        for entry in repo["object"]["entries"]:
                            if entry["name"].lower() == "readme.md":
                                readme_content = entry["object"]["text"]
                            if entry["name"].lower() == "makefile":
                                makefile_content = entry["object"]["text"]

                    # Check if "confluence" is present in README
                    if readme_content is not None:
                        for doc, cl in zip(documentation_list, cloud_services_list):
                            if doc.lower() in readme_content.lower():
                                docs.append(doc)
                            if cl.lower() in readme_content.lower():
                                cloud.append(cl)

                    if makefile_content is not None:
                        for framework in frameworks_list:
                            if framework.lower() in makefile_content.lower():
                                frameworks.append(framework)

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
                    "github_pages_url": (
                        repo.get("homepageUrl")
                        if (
                            repo.get("homepageUrl")
                            and "github.io" in repo.get("homepageUrl")
                        )
                        else None
                    ),
                    "last_commit": last_commit_date,
                    "last_commit_author": (
                        {
                            "name": repo["defaultBranchRef"]["target"]["history"][
                                "nodes"
                            ][0]["author"]["name"],
                            "email": (
                                "redacted"
                                if "users.noreply.github.com"
                                in repo["defaultBranchRef"]["target"]["history"][
                                    "nodes"
                                ][0]["author"]["email"]
                                else repo["defaultBranchRef"]["target"]["history"][
                                    "nodes"
                                ][0]["author"]["email"]
                            ),
                        }
                        if repo["defaultBranchRef"]
                        else None
                    ),
                    "technologies": {
                        "languages": languages,
                        "infrastructure_as_code": check_infrastructure_files(
                            repo["object"]["entries"] if repo["object"] else None
                        ),
                        "cloud_providers": check_cloud_providers(
                            repo["object"]["entries"] if repo["object"] else None,
                            readme_content,
                        ),
                        "ci_cd": check_ci_cd(
                            repo["object"]["entries"] if repo["object"] else None
                        ),
                        "documentation": check_documentation(
                            repo["object"]["entries"] if repo["object"] else None
                        ),
                        "testing": check_testing(
                            repo["object"]["entries"] if repo["object"] else None
                        ),
                        "python_dependencies": python_deps if has_python else None,
                        "javascript_dependencies": (
                            javascript_deps if has_javascript else None
                        ),
                    },
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
                1
                for repo in all_repos
                if repo["last_commit"]
                and not repo["is_archived"]
                and (
                    datetime.datetime.now(datetime.timezone.utc)
                    - datetime.datetime.fromisoformat(
                        repo["last_commit"].replace("Z", "+00:00")
                    )
                ).days
                <= 30
            ),
            "active_last_3months": sum(
                1
                for repo in all_repos
                if repo["last_commit"]
                and not repo["is_archived"]
                and (
                    datetime.datetime.now(datetime.timezone.utc)
                    - datetime.datetime.fromisoformat(
                        repo["last_commit"].replace("Z", "+00:00")
                    )
                ).days
                <= 90
            ),
            "active_last_6months": sum(
                1
                for repo in all_repos
                if repo["last_commit"]
                and not repo["is_archived"]
                and (
                    datetime.datetime.now(datetime.timezone.utc)
                    - datetime.datetime.fromisoformat(
                        repo["last_commit"].replace("Z", "+00:00")
                    )
                ).days
                <= 180
            ),
        },
        "stats_archived": {
            "total": archived_repos,
            "private": archived_private,
            "public": archived_public,
            "internal": archived_internal,
            "active_last_month": sum(
                1
                for repo in all_repos
                if repo["last_commit"]
                and repo["is_archived"]
                and (
                    datetime.datetime.now(datetime.timezone.utc)
                    - datetime.datetime.fromisoformat(
                        repo["last_commit"].replace("Z", "+00:00")
                    )
                ).days
                <= 30
            ),
            "active_last_3months": sum(
                1
                for repo in all_repos
                if repo["last_commit"]
                and repo["is_archived"]
                and (
                    datetime.datetime.now(datetime.timezone.utc)
                    - datetime.datetime.fromisoformat(
                        repo["last_commit"].replace("Z", "+00:00")
                    )
                ).days
                <= 90
            ),
            "active_last_6months": sum(
                1
                for repo in all_repos
                if repo["last_commit"]
                and repo["is_archived"]
                and (
                    datetime.datetime.now(datetime.timezone.utc)
                    - datetime.datetime.fromisoformat(
                        repo["last_commit"].replace("Z", "+00:00")
                    )
                ).days
                <= 180
            ),
        },
        "language_statistics_unarchived": language_averages,
        "language_statistics_archived": archived_language_averages,
        "metadata": {
            "last_updated": datetime.datetime.now(datetime.timezone.utc).strftime(
                "%Y-%m-%d"
            )
        },
        "technology_statistics": {
            "infrastructure_as_code": {
                tool: sum(
                    1
                    for repo in all_repos
                    if tool in repo["technologies"]["infrastructure_as_code"]
                )
                for tool in ["Terraform", "CloudFormation", "Kubernetes", "Ansible"]
            },
            "cloud_providers": {
                provider: sum(
                    1
                    for repo in all_repos
                    if provider in repo["technologies"]["cloud_providers"]
                )
                for provider in ["AWS", "GCP", "Azure"]
            },
            "ci_cd": {
                tool: sum(
                    1 for repo in all_repos if tool in repo["technologies"]["ci_cd"]
                )
                for tool in [
                    "GitHub Actions",
                    "Jenkins",
                    "CircleCI",
                    "Travis CI",
                    "Concourse",
                ]
            },
            "documentation": {
                tool: sum(
                    1
                    for repo in all_repos
                    if tool in repo["technologies"]["documentation"]
                )
                for tool in [
                    "Documentation Directory",
                    "Jekyll",
                    "Sphinx",
                    "MkDocs",
                    "Docusaurus",
                    "Markdown Documentation",
                ]
            },
            "testing": {
                type: sum(
                    1 for repo in all_repos if type in repo["technologies"]["testing"]
                )
                for type in ["Test Directory", "Test Files", "Testing Framework"]
            },
            "python_package_managers": {
                manager: sum(
                    1
                    for repo in all_repos
                    if repo["technologies"].get("python_dependencies")
                    and manager
                    in repo["technologies"]["python_dependencies"]["package_manager"]
                )
                for manager in ["pip", "poetry", "pipenv", "conda", "setuptools"]
            },
            "javascript_frameworks": {
                framework: sum(
                    1
                    for repo in all_repos
                    if repo["technologies"].get("javascript_dependencies")
                    and framework
                    in repo["technologies"]["javascript_dependencies"]["frameworks"]
                )
                for framework in [
                    "react",
                    "vue",
                    "angular",
                    "svelte",
                    "express",
                    "nest",
                    "jquery",
                    "next.js",
                    "gatsby",
                ]
            },
            "javascript_package_managers": {
                manager: sum(
                    1
                    for repo in all_repos
                    if repo["technologies"].get("javascript_dependencies")
                    and manager
                    in repo["technologies"]["javascript_dependencies"][
                        "package_manager"
                    ]
                )
                for manager in ["npm", "yarn", "pnpm"]
            },
        },
    }

    # Write everything to file at once
    with open("repositories.json", "w") as file:
        json.dump(output, file, indent=2)
        file.write("\n")

    return all_repos


def main():
    """Main function to run the GitHub technology audit"""
    try:
        # Configuration
        org = os.getenv("GITHUB_ORG")
        client_id = os.getenv("GITHUB_APP_CLIENT_ID")
        secret_name = os.getenv("AWS_SECRET_NAME")
        secret_region = os.getenv("AWS_DEFAULT_REGION")

        logger.info("Starting GitHub technology audit")

        # Set up AWS session
        session = boto3.Session()
        secret_manager = session.client("secretsmanager", region_name=secret_region)

        # Get GitHub token
        logger.info("Getting GitHub token from AWS Secrets Manager")
        secret = secret_manager.get_secret_value(SecretId=secret_name)["SecretString"]

        token = get_token_as_installation(org, secret, client_id)
        if not token:
            logger.error("Error getting GitHub token")
            return {"statusCode": 500, "body": json.dumps("Failed to get GitHub token")}

        logger.info("Successfully obtained GitHub token")
        ql = github_graphql_interface(str(token[0]))

        # Get repository technology information
        repos = get_repository_technologies(ql, org)

        # Print or save results
        output = {
            "message": "Successfully analyzed repository technologies",
            "repository_count": len(repos),
            "repositories": repos,
        }

    except Exception as e:
        logger.error("Execution failed: %s", str(e))


if __name__ == "__main__":
    main()
