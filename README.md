# GitHub Scraper Lambda

Current version does not use Lambda, it is just a script that can be run locally.

This project utilises the [GitHub API Package](https://github.com/ONS-Innovation/github-api-package) GraphQL interface to get data from GitHub.

The script is run from the command line using the following command:

### Prerequisites:
- Python 3.10+
- Poetry

### Getting started

Setup:
```bash
make install
```

Export environment variables:
```bash
export AWS_ACCESS_KEY_ID=<KEY>
export AWS_SECRET_ACCESS_KEY=<SECRET>
export GITHUB_APP_CLIENT_ID=<CLIENT_ID>
export AWS_DEFAULT_REGION=<REGION>
export AWS_SECRET_NAME=/<env>/github-tooling-suite/<onsdigital/ons-innovation>
export GITHUB_ORG=<onsdigital/ons-innovation>
export SOURCE_BUCKET=<sdp-dev-tech-radar>
export SOURCE_KEY=<repositories.json>
```

To run locally, you need to add this code to the end of the file in app.py:
```python
handler(None, None)
```

Then you can run the script locally:
```bash
make run
```

### Linting and formatting

Install dev dependencies:
```bash
make install-dev
```

Run lint command:
```bash
make lint
```

Run ruff check:
```bash
make ruff
```

Run pylint:
```bash
make pylint
```

Run black:
```bash
make black
```




