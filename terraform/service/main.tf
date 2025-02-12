resource "aws_lambda_function" "github_scraper_lambda" {
  function_name = "${var.domain}-${var.service_subdomain}-lambda"
  package_type  = "Image"
  image_uri     = "${var.aws_account_id}.dkr.ecr.${var.region}.amazonaws.com/${var.ecr_repository_name}:${var.container_ver}"
  
  role = aws_iam_role.lambda_execution_role.arn

  logging_config {
    log_format = "Text"
  }
  
  vpc_config {
    subnet_ids         = data.terraform_remote_state.vpc.outputs.private_subnets
    security_group_ids = [aws_security_group.lambda_sg.id]
  }

  memory_size = 128
  timeout     = 900

  environment {
    variables = {
      SOURCE_BUCKET      = var.source_bucket
      SOURCE_KEY         = var.source_key
      GITHUB_APP_CLIENT_ID = var.github_app_client_id
      AWS_SECRET_NAME = var.aws_secret_name
      GITHUB_ORG = var.github_org
      BATCH_SIZE = var.batch_size
    }
  }

  depends_on = [
    aws_iam_role_policy.lambda_ecr_policy,
    aws_iam_role_policy.lambda_s3_access,
    aws_iam_role_policy.lambda_additional_permissions,
    aws_iam_role_policy.lambda_vpc_permissions,
    aws_iam_role_policy_attachment.lambda_basic_execution
  ]
}

# Add ECR policy after the lambda function is created
resource "aws_ecr_repository_policy" "lambda_ecr_access" {
  repository = var.ecr_repository_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "LambdaECRAccess"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
          AWS = aws_iam_role.lambda_execution_role.arn
        }
        Action = [
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer"
        ]
      }
    ]
  })

  depends_on = [aws_iam_role.lambda_execution_role]
}