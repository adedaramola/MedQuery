# ──────────────────────────────────────────────────────────
# ECS Task Execution Role
# Used by the ECS agent to pull images from ECR and write
# logs to CloudWatch. AWS managed policy covers both.
# ──────────────────────────────────────────────────────────
resource "aws_iam_role" "ecs_execution" {
  name = "${var.app_name}-ecs-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution_managed" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Allow the execution role to read our secrets from Secrets Manager
resource "aws_iam_role_policy" "ecs_execution_secrets" {
  name = "${var.app_name}-read-secrets"
  role = aws_iam_role.ecs_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ]
      Resource = concat(
        [
          aws_secretsmanager_secret.openai_api_key.arn,
          aws_secretsmanager_secret.db_url.arn,
        ],
        var.app_api_key != "" ? [aws_secretsmanager_secret.app_api_key[0].arn] : []
      )
    }]
  })
}

# ──────────────────────────────────────────────────────────
# ECS Task Role
# Attached to the running container. Add permissions here
# if the app needs to call other AWS services (e.g. S3, SES).
# ──────────────────────────────────────────────────────────
resource "aws_iam_role" "ecs_task" {
  name = "${var.app_name}-ecs-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# ──────────────────────────────────────────────────────────
# GitHub Actions CI User
# Least-privilege IAM user for the CI/CD pipeline.
# Permissions: push images to ECR + trigger ECS redeployments.
# After terraform apply, copy the outputs into GitHub repository secrets.
# ──────────────────────────────────────────────────────────
resource "aws_iam_user" "github_ci" {
  name = "${var.app_name}-github-ci"
  tags = { Name = "${var.app_name}-github-ci" }
}

resource "aws_iam_user_policy" "github_ci" {
  name = "${var.app_name}-github-ci-policy"
  user = aws_iam_user.github_ci.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:PutImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecs:UpdateService",
          "ecs:DescribeServices",
          "ecs:DescribeTaskDefinition",
          "ecs:RegisterTaskDefinition"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_access_key" "github_ci" {
  user = aws_iam_user.github_ci.name
}

# Allow the task to write logs directly (belt-and-suspenders with execution role)
resource "aws_iam_role_policy" "ecs_task_logs" {
  name = "${var.app_name}-task-logs"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ]
      Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/ecs/${var.app_name}*"
    }]
  })
}
