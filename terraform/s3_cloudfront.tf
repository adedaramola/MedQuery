# ──────────────────────────────────────────────────────────
# S3 Bucket — React static build artefacts
# ──────────────────────────────────────────────────────────

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "frontend" {
  bucket = "${var.app_name}-frontend-${random_id.bucket_suffix.hex}"
  tags   = { Name = "${var.app_name}-frontend" }
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket                  = aws_s3_bucket.frontend.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  versioning_configuration { status = "Enabled" }
}

# ──────────────────────────────────────────────────────────
# CloudFront Origin Access Control (OAC)
# ──────────────────────────────────────────────────────────
resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${var.app_name}-oac"
  description                       = "OAC for Medical RAG frontend"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# S3 bucket policy — only CloudFront (via OAC) can read objects
resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowCloudFrontServicePrincipal"
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.frontend.arn}/*"
      Condition = {
        StringEquals = {
          "AWS:SourceArn" = aws_cloudfront_distribution.frontend.arn
        }
      }
    }]
  })
}

# ──────────────────────────────────────────────────────────
# CloudFront Distribution
#
# Two origins:
#   s3-frontend  → S3 bucket (React static files, default)
#   alb-backend  → ALB (FastAPI, matched on /api/* path)
#
# This routes all /api/* requests through CloudFront over HTTPS,
# avoiding mixed-content browser errors when the frontend is on HTTPS.
# ──────────────────────────────────────────────────────────
resource "aws_cloudfront_distribution" "frontend" {
  enabled             = true
  default_root_object = "index.html"
  price_class         = "PriceClass_100"
  comment             = "${var.app_name} frontend"

  # Origin 1: S3 (React build)
  origin {
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id                = "s3-frontend"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  # Origin 2: ALB (FastAPI backend)
  # CloudFront connects to the ALB over HTTP; the browser-to-CloudFront
  # leg is always HTTPS — this resolves the mixed-content issue.
  origin {
    domain_name = aws_lb.backend.dns_name
    origin_id   = "alb-backend"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  # Ordered behavior: /api/* → ALB (evaluated before the default)
  ordered_cache_behavior {
    path_pattern           = "/api/*"
    target_origin_id       = "alb-backend"
    viewer_protocol_policy = "redirect-to-https"

    # Allow all HTTP methods so POST /api/query works
    allowed_methods = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods  = ["GET", "HEAD"]

    # Forward everything to the backend — headers, query strings, cookies
    forwarded_values {
      query_string = true
      headers      = ["*"]
      cookies { forward = "all" }
    }

    # Never cache API responses at the edge
    min_ttl     = 0
    default_ttl = 0
    max_ttl     = 0
  }

  # Default behavior: all other paths → S3 (React static files)
  default_cache_behavior {
    target_origin_id       = "s3-frontend"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    forwarded_values {
      query_string = false
      cookies { forward = "none" }
    }

    min_ttl     = 0
    default_ttl = 86400
    max_ttl     = 31536000
  }

  # Return index.html for 403/404 so React client-side routing works
  custom_error_response {
    error_code         = 403
    response_code      = 200
    response_page_path = "/index.html"
  }

  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
  }

  restrictions {
    geo_restriction { restriction_type = "none" }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = { Name = "${var.app_name}-cloudfront" }
}
