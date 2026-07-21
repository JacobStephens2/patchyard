data "aws_iam_policy_document" "route53_records" {
  statement {
    sid = "ManageEtaRecords"
    actions = [
      "route53:ChangeResourceRecordSets",
      "route53:ListResourceRecordSets",
    ]
    resources = ["arn:aws:route53:::hostedzone/${var.eta_zone_id}"]
  }

  statement {
    sid       = "ReadRecordChangeStatus"
    actions   = ["route53:GetChange"]
    resources = ["arn:aws:route53:::change/*"]
  }
}

resource "aws_iam_policy" "route53_records" {
  name_prefix = "route53-patchyard-create-read-"
  description = "Manage the full Route 53 record lifecycle in the example.com hosted zone."
  policy      = data.aws_iam_policy_document.route53_records.json

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_iam_user_policy_attachment" "route53_records" {
  user       = "orchestrator-route53"
  policy_arn = aws_iam_policy.route53_records.arn
}

resource "aws_route53_record" "factory" {
  zone_id = var.eta_zone_id
  name    = "factory.example.com"
  type    = "A"
  ttl     = 300
  records = [var.control_plane_ipv4]
}
