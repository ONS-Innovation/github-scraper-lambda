terraform {
  backend "s3" {
    # Backend is selected using terraform init -backend-config=path/to/backend-<env>.tfbackend
    # bucket         = "sdp-dev-tf-state"
    # key            = "sdp-dev-github-scraper-lambda/terraform.tfstate"
    # region         = "eu-west-2"
    # dynamodb_table = "terraform-state-lock"
  }

}

resource "aws_iam_role" "lambda_execution_role" {
  name = "${var.domain}-${var.service_subdomain}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
  depends_on = [aws_iam_role.lambda_execution_role]
}

resource "aws_iam_role_policy" "lambda_ecr_policy" {
  name = "${var.domain}-${var.service_subdomain}-policy"
  role = aws_iam_role.lambda_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetAuthorizationToken"
        ]
        Resource = [
          "arn:aws:ecr:${var.region}:${var.aws_account_id}:repository/${var.ecr_repository_name}",
          "arn:aws:ecr:${var.region}:${var.aws_account_id}:repository/${var.ecr_repository_name}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken"
        ]
        Resource = "*"
      }
    ]
  })
  depends_on = [aws_iam_role.lambda_execution_role]
}

resource "aws_iam_role_policy" "lambda_s3_access" {
  name = "${var.domain}-${var.service_subdomain}-lambda-s3-policy"
  role = aws_iam_role.lambda_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::${var.source_bucket}",
          "arn:aws:s3:::${var.source_bucket}/*"
        ]
      }
    ]
  })
  depends_on = [aws_iam_role.lambda_execution_role]
}

resource "aws_iam_role_policy" "lambda_additional_permissions" {
  name = "${var.domain}-${var.service_subdomain}-policy-2"
  role = aws_iam_role.lambda_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup"
        ]
        Resource = "arn:aws:logs:${var.region}:${var.aws_account_id}:*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = [
          "arn:aws:logs:${var.region}:${var.aws_account_id}:log-group:/aws/lambda/${var.domain}-${var.service_subdomain}:*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:*",
          "s3-object-lambda:*"
        ]
        Resource = "*"
      }
    ]
  })
  depends_on = [aws_iam_role.lambda_execution_role]
}

resource "aws_iam_role_policy" "lambda_vpc_permissions" {
  name   = "${var.domain}-${var.service_subdomain}-vpc-policy"
  role   = aws_iam_role.lambda_execution_role.id
  policy = data.aws_iam_policy_document.vpc_permissions.json
}

resource "aws_security_group" "lambda_sg" {
  name        = "${var.domain}-${var.service_subdomain}-lambda-sg"
  description = "Security group for ${var.domain}-${var.service_subdomain} Lambda function"
  vpc_id      = data.terraform_remote_state.vpc.outputs.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.domain}-${var.service_subdomain}-lambda-sg"
  }
}


resource "aws_lambda_function" "github_scraper_lambda" {
  function_name = "${var.domain}-${var.service_subdomain}"
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

  memory_size = var.memory_size
  timeout     = var.timeout
  
  environment {
    variables = {
      SOURCE_BUCKET      = var.source_bucket
      GITHUB_APP_CLIENT_ID = var.github_app_client_id
      AWS_SECRET_NAME = var.aws_secret_name
      GITHUB_ORG = var.github_org
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

# 7. Add ECR policy after the lambda function is created
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
