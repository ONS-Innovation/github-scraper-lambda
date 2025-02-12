output "lambda_name" {
  value = aws_lambda_function.github_scraper_lambda.function_name
}

output "lambda_image" {
  value = aws_lambda_function.github_scraper_lambda.image_uri
}

output "lambda_role" {
  value = aws_lambda_function.github_scraper_lambda.role
}

output "repo_name" {
  value = var.ecr_repository_name
}

output "rule_arn" {
  value = aws_cloudwatch_event_rule.daily_trigger.arn
}
