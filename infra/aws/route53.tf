resource "aws_iam_policy" "route53_records" {
  name_prefix = "route53-patchyard-create-read-"
  description = "Manage the full Route 53 record lifecycle in the example.com hosted zone."
  tags        = {}
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadAllZonesAndRecords"
        Effect = "Allow"
        Action = [
          "route53:ListHostedZones",
          "route53:ListHostedZonesByName",
          "route53:GetHostedZone",
          "route53:ListResourceRecordSets",
          "route53:GetChange",
        ]
        Resource = "*"
      },
      {
        Sid    = "ManageRecordsFactoryZone"
        Effect = "Allow"
        Action = [
          "route53:ChangeResourceRecordSets",
          "route53:ListResourceRecordSets",
        ]
        Resource = "arn:aws:route53:::hostedzone/${var.eta_zone_id}"
      },
      {
        Sid      = "GetChangeStatus"
        Effect   = "Allow"
        Action   = "route53:GetChange"
        Resource = "arn:aws:route53:::change/*"
      },
    ]
  })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_iam_user_policy_attachment" "route53_records" {
  user       = "orchestrator-route53"
  policy_arn = aws_iam_policy.route53_records.arn

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "factory" {
  provider = aws.route53

  zone_id = var.eta_zone_id
  name    = "factory.example.com"
  type    = "A"
  ttl     = 300
  records = [var.control_plane_ipv4]
}
