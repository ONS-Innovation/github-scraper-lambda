resource "aws_cloudwatch_event_rule" "daily_trigger" {
  name                = "${var.domain}-${var.service_subdomain}-daily-trigger"
  description         = "Triggers ${var.domain}-${var.service_subdomain}-lambda."
  schedule_expression = var.schedule
}

resource "aws_cloudwatch_event_target" "lambda_target" {
  rule      = aws_cloudwatch_event_rule.daily_trigger.name
  target_id = "${var.domain}-${var.service_subdomain}-lambda"
  arn       = aws_lambda_function.github_scraper_lambda.arn
}

# Permission for EventBridge to invoke Lambda
resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.github_scraper_lambda.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_trigger.arn
} 