# Use an official Python runtime as a parent image
FROM public.ecr.aws/lambda/python:3.12

# Install Poetry
RUN pip install poetry

# Copy the project files
COPY pyproject.toml poetry.lock ${LAMBDA_TASK_ROOT}/

# Install dependencies using Poetry
WORKDIR ${LAMBDA_TASK_ROOT}
RUN poetry config virtualenvs.create false && poetry install --no-root --only main

# Copy the application code
COPY app.py ${LAMBDA_TASK_ROOT}/


# Set the CMD to your handler
CMD [ "app.handler" ]
