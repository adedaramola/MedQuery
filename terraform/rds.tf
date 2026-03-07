# ──────────────────────────────────────────────────────────
# RDS — PostgreSQL 16 with pgvector extension
#
# Replaces both ChromaDB (EFS) and SQLite (EFS) with a single
# managed database. Runs in private subnets; accessible only
# from ECS tasks via the rds security group.
# ──────────────────────────────────────────────────────────

resource "aws_db_subnet_group" "main" {
  name        = "${var.app_name}-db-subnet-group"
  subnet_ids  = aws_subnet.private[*].id
  description = "Private subnets for RDS"

  tags = { Name = "${var.app_name}-db-subnet-group" }
}

resource "aws_db_instance" "postgres" {
  identifier = "${var.app_name}-postgres"

  engine               = "postgres"
  engine_version       = "16.13"
  instance_class       = var.db_instance_class
  allocated_storage    = 20
  max_allocated_storage = 100  # auto-scaling up to 100 GiB
  storage_type         = "gp3"
  storage_encrypted    = true

  db_name  = "medical_rag"
  username = "medical_rag_user"
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  # pgvector is bundled in the postgres16 parameter group — no extra setup
  parameter_group_name = aws_db_parameter_group.postgres.name

  # Backups
  backup_retention_period = 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "sun:04:00-sun:05:00"

  # Availability
  multi_az            = false  # set to true for production HA
  publicly_accessible = false

  # Protect against accidental deletion
  deletion_protection      = true
  skip_final_snapshot      = false
  final_snapshot_identifier = "${var.app_name}-postgres-final-snapshot"

  tags = { Name = "${var.app_name}-postgres" }
}

resource "aws_db_parameter_group" "postgres" {
  name   = "${var.app_name}-postgres16"
  family = "postgres16"

  # shared_preload_libraries is a static parameter — requires pending-reboot apply method
  parameter {
    name         = "shared_preload_libraries"
    value        = "pg_stat_statements"
    apply_method = "pending-reboot"
  }

  tags = { Name = "${var.app_name}-postgres16" }
}
